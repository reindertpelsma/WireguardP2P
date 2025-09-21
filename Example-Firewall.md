# Example firewall and routing rules

This is an example list of rules/firewalls you can apply to ensure both the P2P and the proxied config and clients are isolated.

On the public server add the following to its wg config and restart wg:
 
```
[Interface]
...
Tables=off 
PostUp = /etc/wg-publisher/routes-up.sh
PostDown = /etc/wg-publisher/routes-down.sh
```

Then apply the following iptables rules on the public server

```bash
sudo bash -c 'echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf && sysctl -p'
sudo iptables -N WIREGUARD_FORWARD
sudo iptables -A WIREGUARD_FORWARD -p icmp -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.19.1 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.20.1 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.19.2 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.20.2 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.19.0/24 -j REJECT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.20.0/24 -j REJECT
sudo iptables -A WIREGUARD_FORWARD -j ACCEPT
sudo iptables -A FORWARD -i wg0 -o wg0 -j WIREGUARD_FORWARD 
sudo iptables -P FORWARD DROP
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT # if you want to have secure SSH access to your VPS. Its generally safe to expose pubkey SSH to WAN.
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
sudo iptables -A INPUT -i wg0 -p tcp --dport 8080 -s 192.168.20.1 -d 192.168.20.2 -j ACCEPT # this is the HTTP endpoint that advertises wireguard endpoints for P2P.
sudo iptables -A INPUT -p icmp -j ACCEPT # if you want pings from WAN
sudo iptables -P INPUT DROP
sudo apt install -y iptables-persistent
sudo bash -c "iptables-save > /etc/iptables/rules.v4"
```

Put the following script in /etc/wg-publisher/routes-up.sh on the public server:

```bash
#!/bin/bash
set -e
sudo ip rule add from 192.168.19.0/24 table 100 # this ensures 0.0.0.0/0 is routed to VPS if its comming from proxied clients.
sudo ip rule add from 192.168.20.0/24 table 100
sudo ip route add default dev wg0 table 100
```

Put the following script in /etc/wg-publisher/routes-down.sh on the public server:

```bash
#!/bin/bash
sudo ip rule del from 192.168.19.0/24 table 100
sudo ip rule del from 192.168.20.0/24 table 100
sudo ip route del default dev wg0 table 100
```

Ensure `chmod +x /etc/wg-publisher/routes-up.sh` and `chmod +x /etc/wg-publisher/routes-down.sh`

This ensures there is a proper isolation between the remote clients and correct routing for the proxied config to proxy all traffic back to the remote device.

on the remote device you do something like as follow (edit to your interface names or add rules to restrict access of wg clients):

```bash
sudo bash -c 'echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf && sysctl -p'
sudo iptables -A FORWARD -i wg0 -o wg0 -j REJECT
sudo iptables -A FORWARD -i wg0 -j ACCEPT
sudo iptables -A FORWARD -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A FORWARD -o wg0 -j REJECT
sudo iptables -P FORWARD DROP
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT # if you have SSH with pubkey auth, e.g accessible over local network or over wireguard.
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT # we do not want that the server's firewall is uneccessary blocking inbound connections as well for wireguard
sudo iptables -A INPUT -p icmp -j ACCEPT
sudo iptables -P INPUT DROP
sudo apt install -y iptables-persistent
sudo bash -c "iptables-save > /etc/iptables/rules.v4"
```

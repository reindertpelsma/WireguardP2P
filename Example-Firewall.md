# Example firewall and routing rules

This is an example list of firewall and routing rules you can apply to ensure both the P2P and the proxied configs and clients are isolated. Feel free to adapt these to any firewall tool you prefer.

On the public server add the following to its WireGuard config and restart WireGuard:

```ini
[Interface]
...
Tables=off
PostUp = /etc/wg-publisher/routes-up.sh
PostDown = /etc/wg-publisher/routes-down.sh
```

Then apply the following `iptables` rules on the public server:

```bash
sudo bash -c 'echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf && sysctl -p'
sudo iptables -N WIREGUARD_FORWARD
sudo iptables -A WIREGUARD_FORWARD -p icmp -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
# Allow traffic to the device and server IPs
sudo iptables -A WIREGUARD_FORWARD -d 192.168.19.1 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.20.1 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.19.2 -j ACCEPT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.20.2 -j ACCEPT
# Reject traffic between wireguard clients
sudo iptables -A WIREGUARD_FORWARD -d 192.168.19.0/24 -j REJECT
sudo iptables -A WIREGUARD_FORWARD -d 192.168.20.0/24 -j REJECT
sudo iptables -A WIREGUARD_FORWARD -j ACCEPT
sudo iptables -A FORWARD -i wg0 -o wg0 -j WIREGUARD_FORWARD
sudo iptables -P FORWARD DROP
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT  # allow SSH (pubkey recommended)
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
sudo iptables -A INPUT -i wg0 -p tcp --dport 8080 -s 192.168.20.1 -d 192.168.20.2 -j ACCEPT  # HTTP endpoint that advertises WireGuard endpoints for P2P
sudo iptables -A INPUT -p icmp -j ACCEPT  # allow ping from WAN if desired
sudo iptables -P INPUT DROP
sudo apt install -y iptables-persistent
sudo bash -c "iptables-save > /etc/iptables/rules.v4"
```

Put the following script in `/etc/wg-publisher/routes-up.sh` on the public server:

```bash
#!/bin/bash
set -e
# route traffic from the proxied and P2P subnets via a separate routing table so their default goes out the WireGuard interface
ip rule add from 192.168.19.0/24 table 100
ip rule add from 192.168.20.0/24 table 100
ip route add default dev wg0 table 100
```

Put the following script in `/etc/wg-publisher/routes-down.sh` on the public server:

```bash
#!/bin/bash
set -e
ip rule del from 192.168.19.0/24 table 100 || true
ip rule del from 192.168.20.0/24 table 100 || true
ip route del default dev wg0 table 100 || true
```

Ensure the scripts are executable:

```bash
sudo chmod +x /etc/wg-publisher/routes-up.sh /etc/wg-publisher/routes-down.sh
```

These rules provide isolation between remote clients and ensure correct routing for proxied clients whose traffic should be proxied back to the remote device via the public server.

On the remote device a minimal example (edit interface names and adjust rules to your needs):

```bash
sudo bash -c 'echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf && sysctl -p'
# Reject forwarding between wg clients by default
sudo iptables -A FORWARD -i wg0 -o wg0 -j REJECT
# Allow forwarding from wg0 to other interfaces
sudo iptables -A FORWARD -i wg0 -j ACCEPT
# Allow return traffic to wg0
sudo iptables -A FORWARD -o wg0 -m state --state RELATED,ESTABLISHED -j ACCEPT
# Reject other forwarding to wg0
sudo iptables -A FORWARD -o wg0 -j REJECT
sudo iptables -P FORWARD DROP
# NAT outgoing traffic on the remote device's uplink
sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
# Basic INPUT rules
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT  # allow SSH with pubkey auth if needed
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT  # allow WireGuard
sudo iptables -A INPUT -p icmp -j ACCEPT
sudo iptables -P INPUT DROP
sudo apt install -y iptables-persistent
sudo bash -c "iptables-save > /etc/iptables/rules.v4"
```

Adjust `eth0`, `wg0` and any CIDR ranges to match your topology. These examples aim to be minimal and opinionated; review them before deploying to production.

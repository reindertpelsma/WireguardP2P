# WireguardP2P
Setting up a wireguard connection (VPN) to your device(s) is difficult if its behind NAT or a firewall that blocks inbound connections. This often happens because your device is behind a network like CG-NAT that is not controlled by you, like on cellular.

This project provides a simple python script to directly connect to your device using [UDP Port Punching](https://en.wikipedia.org/wiki/UDP_hole_punching).

If the client IP and server IP are known in advance you can hardcode them both and use [these steps](https://github.com/pirate/wireguard-docs?tab=readme-ov-file#NAT-to-NAT-Connections) to establish a P2P connection, but that does not allow your client to roam for example between your home network, company's wifi and cellular. 

It stands out of any other P2P implementation like [manuels/wireguard-p2p](https://github.com/manuels/wireguard-p2p) because:

1. It does not require installing extra software on the client beside the already widely cross platform compatible wireguard client, it just uses only a simple wireguard config on clients. This makes the setup on the clients far easier. This allows you to use the config for example on your phone where installing python is hard.
2. There is also no third party [STUN](https://en.wikipedia.org/wiki/STUN) protocol involved, the third server just uses wireguard simplifying the setup. This has the advantage that you can always use your public server peer as both for P2P signaling/bootstrap and as relay server in case P2P fails simultaneously.
3. It keeps the roaming feature of wireguard, so if your client moves from network to network, then the connection will automatically re-establish. No need to click reconnect or launch a helper script, everything is done automatically for you.
4. The python script is just 270 lines and you do not need any other tool than wireguard, some linux commands, and python, far simpler than some commercial bloated P2P protocols like WebRTC.
5. All edge cases you might encounter to setup your P2P connection are well explained in this extensive README

# How it works
The server that accepts inbound connection is called in this project the Public server as its firewall is open to the internet, and the device behind firewall is called the Remote Device as its the device you want to connect to. 

Wireguard has the unique ability that a client can connect to multiple peers simultaneously. Every client has 1 peer to the Public server and a peer for every remote device a P2P connection needs to be set up.

The clients create a outbound wireguard connection with the public server using its first peer, while the other peers are in first place primarily used to send a random UDP packet to the remote device endpoints. The python script on this server (wg publisher) will record the client's endpoint IP + port and send it to the remote device's python script (wg subscriber), which will then update its wireguard peer endpoint. This will trigger a packet to be send out to the client creating a UDP punch hole resulting in a fast P2P connection.

# Setup

First generate wireguard private and public key pairs for the public server, all remote devices and all clients.  Use persistent keepalive to ensure the tunnel stays alive behind firewalls.
Then use the following config templates:

## Wireguard config on the public server

```text
[Interface]
PrivateKey=PRIVATE_KEY_PUBLIC_SERVER
Address=192.168.20.2/24, 192.168.19.2/24
ListenPort=51820

# This remote device handles all 0.0.0.0/0 traffic, but you can add more remote devices and device which subnets apply for each one of them.
[Peer]
PublicKey=PUBLIC_KEY_REMOTE_DEVICE
AllowedIPs=0.0.0.0/0
Endpoint=PUBLIC_IP_REMOTE_DEVICE:51820
PersistentKeepalive=10

[Peer]
PublicKey=PUBLIC_KEY_REMOTE_PEER1
AllowedIPs=192.168.20.3/32, 192.168.19.3/32

[Peer]
PublicKey=PUBLIC_KEY_REMOTE_PEER2
AllowedIPs=192.168.20.4/32, 192.168.19.4/32
```

## Wireguard config on the remote device

```text
[Interface]
PrivateKey=PRIVATE_KEY_REMOTE_DEVICE
ListenPort=51820
Address=192.168.20.1/24

[Peer]
PublicKey=PUBLIC_KEY_PUBLIC_SERVER
AllowedIPs=192.168.20.2/32, 192.168.19.0/24
Endpoint=PUBLIC_SERVER_IP:51820
PersistentKeepalive=10

[Peer]
PublicKey=PUBLIC_KEY_REMOTE_PEER1
AllowedIPs=192.168.20.3/32

[Peer]
PublicKey=PUBLIC_KEY_REMOTE_PEER2
AllowedIPs=192.168.20.4/32
```

## P2P wireguard config for the client

```text
[Interface]
PrivateKey=PRIVATE_KEY_PEER1
# Put a random ephermal port in ListenPort, ensure its unique for every client to keep NAT conflicts to the minimum.
# This is to avoid that the wireguard implementation uses a different source port for the two peers, which must be the same to ensure P2P works.
ListenPort=36906
Address=192.168.20.3/24
# DNS=192.168.20.1 # Optionally add DNS

[Peer]
PublicKey=PUBLIC_KEY_PUBLIC_SERVER
AllowedIPs=192.168.20.2/32
Endpoint=PUBLIC_SERVER_IP:51820
PersistentKeepalive=10

[Peer]
PublicKey=PUBLIC_KEY_REMOTE_DEVICE
AllowedIPs=0.0.0.0/0
Endpoint=PUBLIC_IP_REMOTE_DEVICE:51820
PersistentKeepalive=10
```

Its recommended to add a fallback config in case P2P fails for the client, that routes everything through the public server to the remote device.


## Proxied fallback config for the client:

Because P2P connections between computers behind firewalls cannot always be set up reliable it is STRONGLY RECOMMENDED to give every remote client a fallback config that proxies the entire connection over the public server server. To do so, create two subnets, one for P2P clients (e.g 192.168.20.0/24) and one for the proxied clients (e.g 192.168.19.0/24). You can keep the private and public keys obviously. Ensure IP forwarding is enabled on the public server server so that wireguard traffic of proxied clients can go through the remote device peer, see also [Example Firewall](Example-Firewall.md)

If the remote client can't connect with the P2P config, then it can just click on the proxied config which will always work. This is similar to WebRTC fallback with a TURN server, but in this case you do it manually.

```text
[Interface]
PrivateKey=PRIVATE_KEY_PEER1
Address=192.168.19.3/24
# ListenPort is not necessary here as the OS will pick a random one for the only peer to the public server we have
# DNS=192.168.20.1 # Optionally add DNS

[Peer]
PublicKey=PUBLIC_KEY_PUBLIC_SERVER
AllowedIPs=0.0.0.0/0
Endpoint=PUBLIC_SERVER_IP:51820
# PersistentKeepalive=25 # PersistentKeepalive is in this case optional as we do not have to keep the P2P connection alive.
```

In this setup all connected clients with P2P use `192.168.20.0/24` and connected clients using the proxied config (through public server) use `192.168.19.0/24`.

## Setting the python server up

As told, you do not have to install anything else besides these two wireguard configs on the clients, making the setup almost just as easy on clients as without P2P.

The python scripts are usually put in /etc/wg-publisher for wg-publisher (public server) and /etc/wg-subscriber for wg-subscriber (remote device), and the service files can be put in /etc/systemd/system. A random token should be put in /etc/wg-publisher/token.txt or /etc/wg-subscriber/token.txt, e.g generated with `head -c 32 /dev/urandom  | base64`.

In wg-publisher.service you should put a `--exclude-peer` for every public key of a remote device, as their endpoints do not need to be advertised.

Then you initiate the wireguard tunnels and start the python sripts. Clients can now connect with the P2P wireguard config, which should work if the client and server are not behind Symmetric NAT (see reliability), otherwise you can use the proxied config instead.

## Multiple remote devices
It is easy to add multiple remote devices with a shared public server. In that case add for every remote device a tunnel to the server, and let the 'wg subscriber' of every remote device point to the public server local IP (over wireguard)

# Reliability

## IP of remote device
For this setup to work the public IP of the remote device (i.e what is my IP) and public server should be both static and put in the client's wireguard configs. If it is not the case, you should use a DDNS service like [DuckDNS](https://www.duckdns.org/) or host your own and use this domain name instead of the IPs. The DDNS service is generally used when you have inbound connections, but in this case they are also useful for the remote device.

If you use DDNS, you need to ensure a daemon is launched on the remote device (and optionally the public server if its IP is also dynamic) to ensure the DNS record stays fresh whenever a network reset/reboot occurs that usually trigger IP changes.

## Roaming
If the client moves from network to network (i.e its IP update), the P2P connection will be temporarily lost. To ensure a stable connecition, keeping the keepalive intervals short to 10 seconds is crucial on both ends. If a client does move, the endpoint to the public server will update due to wireguard's roaming feature. The public server will record this new endpoint and send this endpoint to the remote device which will re-send a Wireguard handshake packet to the new endpoint, and as the client is also continously sending out packets every few seconds, a P2P connection will be re-established automatically.

The time it takes to re-establish a connection is dependent on the poll intervall of the python script and the KeepAlive interval of the wireguard configs (to both the public server and remote device, on both client config and as set by the python script), whichever is the longest is the maximum time it can take to re-establish a connection, its therefore important to keep them all under 10 seconds.

## NAT types
While this setup does provide great performance and reliability when connected, it does not always guarantee the remote user can use this P2P connection from every kind of connection. This is because how NAT should be performed is not defined and there are many implementations of NAT, most of them are classified by [STUN](https://en.wikipedia.org/wiki/STUN)

If the user is behind Symmetric NAT, meaning its external source port is randomized for every different UDP connection state, then the published endpoint of the user will not match with the endpoint the remote device needs, and the P2P will fail. It is not possible to establish P2P with symmetric NAT, other than brute forcing ports which is impractical. Symmetric NAT is pretty rare as most implementations will attempt to use the same external source port as chosen by the client (i.e Normal NAT), unless it conflicts with an existing state and only then it will randomize due to port collision resolution (like linux's iptables which many routers use under the hood). There are only a few implementations that always do port randomization by default thus Symmetric NAT, like Pfsense.

It seems that cellular networks have the highest chance to use Symmetric NAT, enterprise networks have a moderate chance, while home networks have a very low chance. Here in the netherlands, Symmetric NAT seems to be rare on cellular. To find more about this topic, [read this useful paper](https://arxiv.org/pdf/2311.04658).

If the remote device is behind a router that uses port randomization but its consistent across multiple UDP connections, then P2P will still fail. If only the client is behind such a NAT, then the connection just succeeds, as it is not a requirement that the ListeningPort matches the port the python scripts registers. This is therefore extremely rare, and most implementations either just keep the source port or randomize it for every state.

If the remote device or client does NOT have NAT but is still behind a firewall that blocks inbound connections, for example in networks where clients directly get a public IPv4 assigned, then in that case you are lucky as P2P have even a higher chance to succeed. You do not need any extra configuration on clients or remote device for networks without NAT.

## IPv6
If IPv6 is tunneled inside the wireguard tunnel, then it has no effect on the setup. If IPv6 is used as wireguard endpoints, then this project can still be relevant. Even though IPv6 usually does not use NAT, many still block inbound connections, which can be punch holed to establish a P2P connection. Because IPv6 does not have NAT makes IPv6 better suited for P2P. The project has not been tested with IPv6.

## Hardcoding listening port
It is recommended to hardcode a listening port on the client. This ensures that the client uses the same source port when connecting to both peers (public server and remote device) so the client endpoint matches, despite the fact that most implementations keep the randomized source port consistent across multiple peers when ListeningPort is not specified, its better to fix it as wireguard protocol itself does not explicitly mandate that the source port should be consistent when ListeningPort is not defined.

It should be unique across all your clients, to prevent port collision resolution if two clients are behind the same NAT firewall, as this will prevent the P2P to succeed on both clients simultaneously. Set the ListeningPort in clients for example to 3600+peer index, so 3601, 3602 etc.
.

## Don't let your firewall be the second problem
In many setups you have a second router like a cellular modem or some home/tenant router connected to the ISP/building's CG-NAT infrastructure, meaning you have double NAT: your router and the ISP's router. You probably discovered that you can add a port forward rule in your router to your device but it has no effect as your ISP's firewall is blocking inbound connections, hence you ended up at this project. In that case it is still useful to add a port forward rule even if inbound connections from WAN are blocked, you do not want that your router is also blocking the inbound connection, plus in case the client is already on the internal network such as with Shared Router as explained below, then it can directly reach the remote device's wireguard.

Wireguard is extremely safe to open to WAN or untrusted networks, so you usually do not need to worry about that. It is also important that you ALLOW the wireguard port inbound in the remote device.

## Shared router
If the client and the remote device share the same NAT/firewall router (like you are connected to the same company's infrastructure, Wi-Fi, Cellular network or behind the same CG-NAT), and this router blocks connections between internal networks, then the P2P may fail. It is important to check if direct connections using for example the local IP of the remote device on the shared network is possible, as many do not firewall connections between internal networks explicitly. If this fails, then a regular P2P connection may just succeed even if both the client and remote device share a public IP, because the remote device uses a different listening port as the client and by testing if the port punching works through Hairpin nat.

In the case your client connects/roams to a local network of the remote device, like for example the Wi-Fi of the cellular modem you manage but that modem is behind CG-NAT of the provider, you have the ability to route your tunnel directly to the device without ever using the ISP infrastructure. This results in better reliability but also better performance. There are two main options for this if you control the local network's router, both have an advantage and a drawback:

1. If you use a DDNS service as explained above, usually if your device is connected to something like cellular, you can put a static local DNS record in the local network's router. The client will resolve to the local IP of the device inside the network and connect directly, fast and simple. If the client roams to an external network, it resolves to the public IP and uses P2P. The problem is that the DNS resolve to the IP only takes place when you click connect, or `wg-quick up` as the wireguard kernel module or userspace libraries do not understand DNS and only endpoint IPs, this makes the roaming not seamless.

2. The second elegant option is to put a [DNAT](https://en.wikipedia.org/wiki/Network_address_translation#DNAT), sometimes called (advanced) port forwarding, rule in the local network's router, so that connections to the remote device public IP:wireguard is directly routed to the device instead of sending it out to the cellular network. The problem is that the IP of the remote device may change which is hard to put in a DNAT rule, but the advantage is that this will ensure in a seamless roaming experience without clicking re-connect. Many implementations do support putting a hostname in the DNAT rule, meaning you can still use your DDNS name. Plus the IP assigned to your modem usually only changes when the network resets or your network router reboots. Example of putting DNAT rule in [Pfsense](https://docs.netgate.com/pfsense/en/latest/nat/port-forwards.html) or in [Ubiquiti](https://help.ui.com/hc/en-us/articles/16437942532759-DNAT-SNAT-and-Masquerading-in-UniFi).

3. Sometimes both options are not needed at all. If your local network's router is assigned a public IPv4 directly, even if it has inbound connections blocked, then hairpin NAT (reaching your external IP from withing the network) which is usually enabled by default keeps it working on the local network with public IPs in the configs. Ensure that a port forward in your router is still added as explained in 'Don't let your firewall be the second problem'.

In some cases with a shared router that blocks internal connections the proxied config is the only solution.

## Double persistent keepalive and stale peers
In regular wireguard to a server with inbound connections persistent keepalive of the recommended 25 seconds is only used if a client needs to receive packets (like inbound connections to client or long lived TCP sessions) after the tunnel went silent for more than 30 seconds (default UDP timeout), and only the client has to send these keepalive packets usually as the server should not send packets anymore if a client disconnects from the server. 

In the case of P2P the outbound connection state is needed on both firewalls of the client and remote device, meaning that if the state is purged then all connectivity will be lost. In addition to this, if a client roams between networks both peers need to send a packet to the other endpoint to punch hole a new state, so a PersistentKeepalive is also added by the python script on the remote device.

To prevent sending packets to clients that are disconnected for a while, a timer of by default 120 seconds since the last wireguard handshake will purge the PersistentKeepalive, as wireguard handshakes are usually every 2 minutes.

## Reliable port forward
To establish a more reliable connection you can attempt to port forward on the client side. You probably already checked that port forward was not possible on the remote device networks otherwise you already had inbound connections, but sometimes it is possible to port forward on the clients side.

This is especially useful if the client is primarily connecting from a specific network like a home network, and doing this will not remove the ability to roam to other networks. You can hardcode a port forward in your home's router using its routers web interface provided by the ISP or if you do not have access to it you can check if a port forward is possible through UPnP, NAT-PMP or PCP as many home routers have any of those three protocols exposed and sometimes an enterprise network exposes it too.

Example if the client port is 36906
```bash
# UPnP (miniupnpc)
sudo apt install miniupnpc
upnpc -a 192.168.1.100 36906 36906 UDP      # add
upnpc -l                                   # list
upnpc -d 36906 UDP                         # delete

# NAT-PMP
sudo apt install natpmpc
natpmpc -a 36906 36906 udp 3600            # add 1-hour mapping
natpmpc -a 36906 36906 udp 0               # remove

# PCP (build libpcpnatpmp and use CLI)
git clone https://github.com/libpcpnatpmp/libpcpnatpmp.git
# build per INSTALL.md, then (example)
./cli-client/pcp-client map --proto udp --internal 192.168.1.100 --internal-port 36906 --external-port 36906 --lifetime 3600
```

Don't forget to allow the port in the client's device, if it has a firewall. 

You do not need to hardcode the client's endpoint IP+port in the remote device's config as this will be auto-discovered. One problem that may occur is that the source port to the public server may have been randomized, meaning that the auto discovered endpoint is incorrect. The simple solution if you are behind Symmetric NAT is to create a seperate peer like 'my laptop at home' where the endpoint IP+port is hardcoded in the remote device, and the peer is added to `--exclude-peer`, don't forget that server side PersistentKeepalive is still relevant. Then you can keep an additional 2 configs for P2P and proxied/relayed in case you roam to other networks. Future work could include an update endpoint that a client can invoke to set its endpoint correctly and a python script optionally for the client to automatically test port forwarding through UPnP, nat-pmp or PCP.

## Most important: keep the relayed/proxied fallback
In any case you attempt P2P have the relayed/proxied config to the public server always as fallback ready all times, because you know for sure that this one will always work. This means you never lose access to your remote device, but it might impact performance and bandwidth if its routed to a third server.

# Security
All traffic is end-to-end encrypted with Wireguard between clients and both the public server and the remote device, and UDP punch hole packets are only sent when authorized wireguard clients connect. The python API server to discover endpoints should be ONLY listening on the wireguard interface and ONLY accept connections over the wireguard tunnel from the remote device and should not be exposed to the internet. It is indeed run over http:// but this is not an issue if the connection between the public server and remote device is already encrypted by wireguard. In case someone else on the network could reach this API server, a token.txt is placed to guard access.

Obviously you should use a trusted hosting provider for the public server, as the public server does have access to your local network. But this goes without saying...

# License
This project is licensed under MIT

# Also interesting

[pirate/wireguard-docs](https://github.com/pirate/wireguard-docs): Unofficial documentation for all kinds of wireguard setups

[samyk/pwnat](https://github.com/samyk/pwnat): Works by sending udp packets to some fixed internet IP, and the client replying with ICMP TTL as if it was a router on the path to the host, to discover the client IP+port. Does not require a third server. Still has the issue that if you are behind symmetric NAT, then this will not succeed, and it requires a client application. Many routers will block this kind of ICMP hacking sadly.

[manuels/wireguard-p2p](https://github.com/manuels/wireguard-p2p): Alternative in case you do not want multi peers in your wireguard config, but instead want a simple signaling server, and you accept that clients also need a script (making mobile phones difficult). 

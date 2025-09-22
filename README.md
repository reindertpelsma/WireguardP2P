# WireguardP2P
Setting up a wireguard connection (VPN) to your device(s) is difficult if its behind NAT or a firewall that blocks inbound connections. This often happens because your device is behind a network like CG-NAT that is not controlled by you, like on cellular.

This project provides a simple python script to directly connect to your device using [UDP Port Punching](https://en.wikipedia.org/wiki/UDP_hole_punching).

If the client IP and server IP are known in advance you can hardcode them both and use [these steps](https://github.com/pirate/wireguard-docs?tab=readme-ov-file#NAT-to-NAT-Connections) to establish a P2P connection, but that does not allow your client to roam for example between your home network, company's wifi and cellular. This small python project of just 270 lines dynamically discovers the client IP + port using a third server (the public server) allowing the client to roam between betworks.

It stands out of any other P2P implementation like [manuels/wireguard-p2p](https://github.com/manuels/wireguard-p2p) as it does not require installing extra software on the client beside the already widely cross platform compatible wireguard client, it just uses some simple wireguard config tricks on the client. This makes the setup on the clients far easier. There is also no third party [STUN](https://en.wikipedia.org/wiki/STUN) protocol involved, the third server just uses wireguard simplifying the setup. This has the advantage that you can always use your public server peer as both for P2P signaling and as relay server in case P2P fails.

You still need the linux server (public server) with inbound connections (like a small VPS in the cloud) but it will only be used for bootstrapping the connection.

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
PostUp = /etc/wg-publisher/routes-up.sh
PostDown = /etc/wg-publisher/routes-down.sh

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

## Roaming
If the client moves from network to network (i.e its IP update), the P2P connection will be temporarily lost. To ensure a stable connecition, keeping the keepalive intervals short to 10 seconds is crucial on both ends. If a client does move, the endpoint to the public server will update due to wireguard's roaming feature. The public server will record this new endpoint and send this endpoint to the remote device which will re-send a Wireguard handshake packet to the new endpoint, and as the client is also continously sending out packets every few seconds, a P2P connection will be re-established automatically.

## NAT types
While this setup does provide great performance and reliability when connected, it does not always guarantee the remote user can use this P2P connection from every kind of connection. This is because how NAT should be performed is not defined and there are many implementations of NAT, most of them are classified by [STUN](https://en.wikipedia.org/wiki/STUN)

If the user is behind Symmetric NAT, meaning its external source port is randomized for every different UDP connection state, then the published endpoint of the user will not match with the endpoint the remote device needs, and the P2P will fail. It is not possible to establish P2P with symmetric NAT, other than brute forcing ports which is impractical. Symmetric NAT is pretty rare as most implementations will attempt to use the same external source port as chosen by the client (i.e Normal NAT), unless it conflicts with an existing state and only then it will randomize due to port collision resolution (like linux's iptables which many routers use under the hood). There are only a few implementations that always do port randomization by default thus Symmetric NAT, like Pfsense.

If the remote device is behind a router that uses port randomization but its consistent across multiple UDP connections, then P2P will still fail. If only the client is behind such a NAT, then the connection just succeeds, as it is not a requirement that the ListeningPort matches the port the python scripts registers. This is therefore extremely rare, and most implementations either just keep the source port or randomize it for every state.

If the remote device or client does NOT have NAT but is still behind a firewall that blocks inbound connections, for example in networks where clients directly get a public IPv4 assigned, then in that case you are lucky as P2P have even a higher chance to succeed. You do not need any extra configuration on clients or remote device for networks without NAT.

## IPv6
If IPv6 is tunneled inside the wireguard tunnel, then it has no effect on the setup. If IPv6 is used as wireguard endpoints, then this project can still be relevant. Even though IPv6 usually does not use NAT, many still block inbound connections, which can be punch holed to establish a P2P connection. Because IPv6 does not have NAT makes IPv6 better suited for P2P. The project has not been tested with IPv6.

## Hardcoding listening port
It is recommended to hardcode a listening port on the client. This ensures that the client uses the same source port when connecting to both peers (public server and remote device) so the client endpoint matches, despite the fact that most implementations keep the randomized source port consistent across multiple peers when ListeningPort is not specified, its better to fix it as wireguard protocol itself does not explicitly mandate that the source port should be consistent when ListeningPort is not defined.

It should be unique across all your clients, to prevent port collision resolution if two clients are behind the same NAT firewall, as this will prevent the P2P to succeed on both clients simultaneously. Set the ListeningPort in clients for example to 3600+peer index, so 3601, 3602 etc.
.
## Shared router
If the user and the remote device share on router, and this router blocks connections between internal networks, then the P2P will fails. For example if both devices are connected to the same cellular network or CG-NAT. In that case the proxied config is the only solution.

# Security
All traffic is end-to-end encrypted with Wireguard between clients and both the public server and the remote device, and UDP punch hole packets are only sent when authorized wireguard clients connect. The python API server to discover endpoints should be ONLY listening on the wireguard interface and ONLY accept connections over the wireguard tunnel from the remote device and should not be exposed to the internet. It is indeed run over http:// but this is not an issue if the connection between the public server and remote device is already encrypted by wireguard. In case someone else on the network could reach this API server, a token.txt is placed to guard access.

Obviously you should use a trusted hosting provider for the public server, as the public server does have access to your local network. But this goes without saying...

# License
This project is licensed under MIT


# WireGuardP2P — Seamless Peer-to-Peer WireGuard Connections Behind NAT

Setting up a WireGuard VPN can be a headache when your devices are behind NATs or firewalls that block incoming connections — a common scenario with networks you don’t control, such as those using CG-NAT (typical for many mobile or ISP setups).

**WireGuardP2P** solves that problem with a simple Python script that enables direct, peer-to-peer WireGuard connections using [UDP hole punching](https://en.wikipedia.org/wiki/UDP_hole_punching).
No complex relay setups, no third-party signaling servers — just a lightweight and reliable way to make your devices talk directly.

Normally, you could hardcode the client and server IPs and follow [these manual steps](https://github.com/pirate/wireguard-docs?tab=readme-ov-file#NAT-to-NAT-Connections) to establish a P2P connection. But that breaks down when your client moves between networks — like switching between home Wi-Fi, office Wi-Fi, and cellular — since WireGuard endpoints aren’t stable.

**WireGuardP2P automates all of that:** it dynamically updates the WireGuard configuration on your remote device so you only have to click *Connect* on your client. The rest happens automatically.

# Why WireGuardP2P is Different

1. **Zero extra software on clients.** You only need the standard WireGuard client — no Python or helper tools required. Works even on devices like phones.
2. **No STUN or external signaling servers.** The public peer doubles as a simple WireGuard server for bootstrap and fallback, keeping your setup minimal and predictable.
3. **Full WireGuard roaming support.** Move between networks freely — connections re-establish automatically without reconnecting or restarting anything.
4. **Lightweight and transparent.** The script is only ~270 lines of Python, using nothing beyond WireGuard and standard Linux tools — far simpler than bloated P2P frameworks like WebRTC.
5. **Extensively documented.** Every edge case and NAT scenario is clearly explained in this README.

# How it works

The server that accepts inbound connections is called the *public server* in this project (its firewall is open to the internet). The device behind a firewall is called the *remote device* — it's the device you want to connect to.

WireGuard has the unique ability that a client can connect to multiple peers simultaneously. Every client has one peer to the public server and a peer for every remote device a P2P connection needs to be set up with.

Clients create an outbound WireGuard connection to the public server using their first peer, while the other peers are primarily used to send a random UDP packet to remote device endpoints. The Python script on the public server (wg-publisher) records the client's endpoint IP and port and sends it to the remote device's Python script (wg-subscriber), which then updates its WireGuard peer endpoint. This triggers a packet to be sent out to the client, creating a UDP punch hole and resulting in a fast P2P connection.

---

# Example setup

First generate WireGuard private/public key pairs for the public server, all remote devices and all clients. Use persistent keepalive to ensure the tunnel stays alive behind firewalls. Then use the following config templates.

## WireGuard config on the public server

```text
[Interface]
PrivateKey=PRIVATE_KEY_PUBLIC_SERVER
Address=192.168.20.2/24, 192.168.19.2/24
ListenPort=51820

# This remote device handles all 0.0.0.0/0 traffic, but you can add more remote devices and specify which subnets apply for each one of them.
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

## WireGuard config on the remote device

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

## P2P WireGuard config for the client

```text
[Interface]
PrivateKey=PRIVATE_KEY_PEER1
# Put a random ephemeral port in ListenPort; ensure it's unique for every client to minimize NAT conflicts.
# This avoids the WireGuard implementation using a different source port for the two peers, which must be the same to ensure P2P works.
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

It's recommended to add a fallback config in case P2P fails for the client, that routes everything through the public server to the remote device.

## Proxied fallback config for the client

Because P2P connections between devices behind firewalls cannot always be established reliably, it is **strongly recommended** to give every remote client a fallback config that proxies the entire connection over the public server. To do so, create two subnets: one for P2P clients (e.g. `192.168.20.0/24`) and one for proxied clients (e.g. `192.168.19.0/24`). You can keep the same private and public keys. Ensure IP forwarding is enabled on the public server so that WireGuard traffic of proxied clients can go through the remote device peer (see also [Example Firewall](Example-Firewall.md)).

If the remote client can't connect with the P2P config, it can switch to the proxied config which will always work. This is similar to WebRTC fallback with a TURN server, but in this case you do it manually.

```text
[Interface]
PrivateKey=PRIVATE_KEY_PEER1
Address=192.168.19.3/24
# ListenPort is not necessary here as the OS will pick a random one for the only peer to the public server.
# DNS=192.168.20.1 # Optionally add DNS

[Peer]
PublicKey=PUBLIC_KEY_PUBLIC_SERVER
AllowedIPs=0.0.0.0/0
Endpoint=PUBLIC_SERVER_IP:51820
# PersistentKeepalive=25 # Optional here as we do not have to keep a P2P connection alive.
```

In this setup, all connected clients using P2P use `192.168.20.0/24` and connected clients using the proxied config (through the public server) use `192.168.19.0/24`.

## Setting the Python server up

You do not have to install anything else on clients besides the two WireGuard configs, making the setup almost as easy on clients as without P2P.

The Python scripts are usually placed in `/etc/wg-publisher` for `wg-publisher` (public server) and `/etc/wg-subscriber` for `wg-subscriber` (remote device), and the service files can be placed in `/etc/systemd/system`. A random token should be put in `/etc/wg-publisher/token.txt` or `/etc/wg-subscriber/token.txt`, for example generated with:

```
head -c 32 /dev/urandom | base64
```

In `wg-publisher.service` add a `--exclude-peer` for every public key of a remote device, as their endpoints do not need to be advertised.

Then initiate the WireGuard tunnels and start the Python scripts. Clients can now connect with the P2P WireGuard config, which should work if the client and server are not behind symmetric NAT (see Reliability). Otherwise you can use the proxied config instead.

## Multiple remote devices

It's easy to add multiple remote devices with a shared public server. In that case add for every remote device a tunnel to the server, and have the `wg-subscriber` of every remote device point to the public server's local IP (over WireGuard).

---

# Reliability

## IP of remote device

For this setup to work the public IP of the remote device (i.e. "what is my IP") and the public server should both be static and put in the client's WireGuard configs. If that's not the case, use a DDNS service like [DuckDNS](https://www.duckdns.org/) or host your own and use that domain name instead of IPs. DDNS is generally used when you have inbound connections, but in this case it's also useful for the remote device.

If you use DDNS, ensure a daemon is launched on the remote device (and optionally the public server if its IP is also dynamic) to keep the DNS record fresh whenever a network reset or reboot occurs that would change the IP.

## Roaming

If the client moves between networks (i.e. its IP changes), the P2P connection will be temporarily lost. To ensure a stable connection, keeping the keepalive intervals short (10 seconds) is crucial on both ends. If a client moves, the endpoint to the public server will update due to WireGuard's roaming feature. The public server will record this new endpoint and send it to the remote device which will re‑send a WireGuard handshake packet to the new endpoint. As the client also continuously sends out packets every few seconds, a P2P connection will be re‑established automatically.

The time it takes to re‑establish a connection depends on the poll interval of the Python script and the KeepAlive interval of the WireGuard configs (both for the public server and remote device, on the client config and as set by the Python script). Whichever is the longest is the maximum time it can take to re‑establish a connection, so it's important to keep them all under 10 seconds.

## NAT types

While this setup provides great performance and reliability when it works, it does not always guarantee a P2P connection from every kind of network. That is because NAT behavior is not strictly standardized and many implementations exist — many of which are classified by [STUN](https://en.wikipedia.org/wiki/STUN).

All modern networks have a stateful firewall that either blocks or allows inbound connections for wireguard. Networks with a stateful firewall that blocks inbound connections always fall in the category: port restricted NAT, symmtric firewall or symmetric NAT, because this applies to 99% of the cases, you can basically ignore the other irrelevant legacy cases of 'full cone NAT' or 'restricted cone NAT' that allowed new connection states to be created by changing ports or IPs.

If the user is behind symmetric NAT (i.e. the external source port is randomized for every different UDP connection state), then P2P will fail as the endpoint python registers does not match. It is not possible to establish P2P with symmetric NAT other than brute‑forcing ports, which is impractical.

Clients usually only fail to connect if they're behind true symmetric NAT. There is no restriction that the source port of the client should be the same as the one in the config, or that if a port is allocated inbound connections to that port should be allowed (like full‑cone NAT), only that it's consistent for both the UDP connection to the remote device and to the public server. This means that P2P works for clients up to port‑restricted NAT. There is however a restriction that the port the remote device selected remains the same on the public internet, but on most Normal nats this is the case.

## IPv6

If IPv6 traffic is tunneled inside the WireGuard tunnel, it has no effect on the setup. If IPv6 is used as WireGuard endpoints, this project can still be relevant. Even though IPv6 usually does not use NAT, many networks still block inbound connections; these can be punched through to establish a P2P connection. Because IPv6 does not require NAT, it's better suited for P2P. The project has not been tested with IPv6.

## Hardcoding listening port

It is recommended to hardcode a listening port on the client. This ensures that the client uses the same source port when connecting to both peers (public server and remote device) so the client endpoint matches. Although most implementations keep the randomized source port consistent across multiple peers when `ListenPort` is not specified, it's better to fix it as the WireGuard protocol itself does not explicitly mandate consistency when `ListenPort` is undefined.

The port should be unique across all your clients to prevent port collision resolution if two clients are behind the same NAT/firewall; collisions will prevent P2P from succeeding on both clients simultaneously. Set the `ListenPort` on clients for example to `3600 + peer_index`, so `3601`, `3602`, etc.

## Don't let your firewall be the second problem

First ensure that the Wireguard port is open on the remote device for inbound connections, you do not want an unnecessary firewall here.

In many setups you have a second router (like a cellular modem or a home/tenant router) connected to the ISP/building's CG‑NAT infrastructure — meaning you have double NAT: your router and the ISP's router. In that case it is still useful to add a port forward rule so your router does not block the inbound connection, and in case the client is already on the internal network (see Shared router below) it can directly reach the remote device's WireGuard.

If your local router is doing port randomization like on pfSense, then DISABLE that for all inbound/outbound wireguard connections, as this will break the P2P connectivity.

WireGuard is generally safe to open to WAN or untrusted networks, so you usually do not need to worry about that. 

## Shared (CG-NAT) router

If the client and the remote device share the same NAT/firewall router (for example connected to the same company infrastructure, Wi‑Fi, cellular network, or behind the same CG‑NAT), and this router blocks connections between internal networks, then P2P may fail. It is important to check if direct connections using the local IP of the remote device on the shared network are possible, as many routers do not firewall connections between internal networks explicitly. If this fails, then a regular P2P connection may still succeed even if both the client and remote device share a public IP, because the remote device may use a different listening port than the client and hairpin NAT may allow the port punching to work.

If your client roams to a local network of the remote device (for example the Wi‑Fi of a cellular modem you manage but that modem is behind CG‑NAT of the provider), you can route your tunnel directly to the device without using the ISP infrastructure. This results in better reliability and performance. Two main options exist if you control the local network's router; each has advantages and disadvantages:

1. If you use DDNS as explained above, you can put a static local DNS record in the local router. The client will resolve to the local IP of the device inside the network and connect directly. If the client roams to an external network, it resolves to the public IP and uses P2P. The drawback is that DNS resolution to the IP only takes place when you click *connect* or run `wg-quick up` as the WireGuard kernel module or userspace libraries do not understand DNS in endpoints and only accept IPs; this makes roaming not seamless.

2. A more elegant option is to add a [DNAT](https://en.wikipedia.org/wiki/Network_address_translation#DNAT) rule (advanced port forwarding) in the local router so that connections to the remote device's public IP\:WireGuard port are routed directly to the device instead of being sent out to the cellular network. The problem is that the remote device's public IP may change, which is hard to keep in a DNAT rule; however many router implementations support a hostname in the DNAT rule, so you can still use your DDNS name. Often the IP assigned to your modem only changes when the network resets or the router reboots. Examples: [pfSense port forwards](https://docs.netgate.com/pfsense/en/latest/nat/port-forwards.html) or [Ubiquiti DNAT/SNAT docs](https://help.ui.com/hc/en-us/articles/16437942532759-DNAT-SNAT-and-Masquerading-in-UniFi).

3. Sometimes neither option is needed. If your local router has a public IPv4 directly assigned, hairpin NAT (reaching your external IP from within the network), which is usually enabled by default, will keep it working on the local network with public IPs in the configs. Still ensure that a port forward in your router is added as explained in "Don't let your firewall be the second problem".

In some cases with a shared router that blocks internal connections, the proxied config is the only solution.

## Double persistent keepalive and stale peers

In regular WireGuard to a server with inbound connections, PersistentKeepalive of the recommended 25 seconds is only used if a client needs to receive packets after the tunnel went silent for more than 30 seconds (default UDP timeout). Usually only the client has to send these keepalive packets since the server should not send packets if the client disconnects.

In P2P both outbound connection states are needed on the firewalls of the client and remote device. If the state is purged then all connectivity is lost. If a client roams between networks both peers need to send a packet to the other endpoint to punch a new state, so a PersistentKeepalive is also added by the Python script on the remote device.

To prevent sending packets to clients that have been disconnected for a while, a timer (default 120 seconds since the last WireGuard handshake) will purge the PersistentKeepalive, as WireGuard handshakes are usually every 2 minutes.

## Reliable port forward

To establish a more reliable connection you can attempt to port forward on the client side. You probably already checked that port forward was not possible on the remote device networks; otherwise you'd already have inbound connections. Sometimes it is possible to port forward on the client's side.

This is especially useful if the client primarily connects from a specific network (like a home network); doing so will not remove the ability to roam to other networks. You can hardcode a port forward in your home router using the router's web interface provided by the ISP. If you do not have access to it, check if a port forward is possible through UPnP, NAT‑PMP or PCP, as many home routers expose one of those protocols and sometimes enterprise networks do too.

Example if the client port is `36906`:

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

Don't forget to allow the port in the client's firewall.

You do not need to hardcode the client's endpoint IP+port in the remote device's config as this will be auto‑discovered. One problem that may occur is that the source port to the public server may have been randomized, meaning that the auto‑discovered endpoint is incorrect. The simple solution if you are behind symmetric NAT is to create a separate peer (for example `my-laptop-at-home`) where the endpoint IP+port is hardcoded in the remote device, and add that peer to `--exclude-peer`. Don't forget that server‑side PersistentKeepalive is still relevant. Then you can keep an additional two configs for P2P and proxied/relayed use in case you roam to other networks. Future work could include an update endpoint that a client can invoke to set its endpoint correctly and an optional Python script for the client to automatically test port forwarding through UPnP, NAT‑PMP or PCP.

## Most important: keep the relayed/proxied fallback

Always keep the relayed/proxied config to the public server ready as a fallback because you know for sure that this will work. This means you never lose access to your remote device, though it might impact performance and bandwidth if traffic is routed through a third server.

---

# Security

All traffic is end‑to‑end encrypted with WireGuard between clients and both the public server and the remote device. UDP punch‑hole packets are only sent when authorized WireGuard clients connect. The Python API server used to discover endpoints should **only** listen on the WireGuard interface and **only** accept connections over the WireGuard tunnel from authorized peers; it should not be exposed to the internet. It runs over HTTP, but this is acceptable if the connection between the public server and remote device is already encrypted by WireGuard. To further protect access, a `token.txt` is used to guard the API.

Obviously you should use a trusted hosting provider for the public server, as the public server can access your local network.

---

# License

This project is licensed under the MIT License.

---

# Also interesting

* [pirate/wireguard-docs](https://github.com/pirate/wireguard-docs): Unofficial documentation for many WireGuard setups.
* [samyk/pwnat](https://github.com/samyk/pwnat): Works by sending UDP packets to a fixed internet IP; the client replies with ICMP TTL as if it were a router on the path to the host to discover the client IP+port. Does not require a third server but still fails behind symmetric NAT and requires a client application. Many routers block this kind of ICMP activity.
* [manuels/wireguard-p2p](https://github.com/manuels/wireguard-p2p): Alternative if you don't want multiple peers in your WireGuard config, but instead want a simple signaling server and accept that clients need a script (which makes mobile phones harder).

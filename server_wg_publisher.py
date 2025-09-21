#!/usr/bin/env python3
"""
server_wg_publisher.py

To establish P2P connections between Remote client and the server even if both are behind firewalls that block inbound connections

Serves a small authenticated HTTP JSON API over the WireGuard tunnel only.

Usage example:
  sudo /usr/local/bin/server_wg_publisher.py \
    --interface wg0 \
    --bind-ip 192.168.20.2 \
    --port 8080 \
    --token-file /etc/wg-publisher/token.txt \
    --exclude-peer <REMOTE_DEVICE_PUBLIC_KEY>

Notes:
 - Bind IP should be the VPS's WireGuard IP (e.g. 192.168.20.2). This prevents the API from
   being reachable on public interfaces.
 - API security: token-file must be readable only by the service user (chmod 600).
 - This intentionally does NOT enable TLS because the WireGuard tunnel provides confidentiality.
"""
import argparse
import subprocess
import time
from flask import Flask, jsonify, request, abort

app = Flask(__name__)

def run_wg_dump(iface: str) -> str:
    proc = subprocess.run(["wg", "show", iface, "dump"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout

def parse_wg_dump(dump_text: str):
    lines = [l for l in dump_text.splitlines() if l.strip()]
    if not lines:
        return []
    peers = []
    # skip first (interface) line
    for pline in lines[1:]:
        parts = pline.split()
        if len(parts) < 8:
            continue
        pubkey = parts[0]
        #preshared = parts[1] if parts[1] != '-' else None
        endpoint = parts[2] if parts[2] != '-' else None
        allowed_ips = parts[3].split(',') if parts[3] != '-' else []
        try:
            latest_handshake = int(parts[4])
        except Exception:
            latest_handshake = 0
        try:
            rx = int(parts[5]); tx = int(parts[6])
        except Exception:
            rx = tx = 0
        try:
            pka = int(parts[7]) if parts[7] != '-' else None
        except Exception:
            pka = None
        peers.append({
            "public_key": pubkey,
            #"preshared_key": preshared,
            "endpoint": endpoint,
            "allowed_ips": allowed_ips,
            "latest_handshake": latest_handshake,
            "rx_bytes": rx,
            "tx_bytes": tx,
            "persistent_keepalive": pka
        })
    return peers

def load_token(path):
    with open(path, "r") as fh:
        return fh.read().strip()

@app.route("/api/peers", methods=["GET"])
def api_peers():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        abort(401)
    token = auth.split(None, 1)[1].strip()
    if token != app.config["API_TOKEN"]:
        abort(403)
    iface = app.config["INTERFACE"]
    try:
        dump = run_wg_dump(iface)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    peers = parse_wg_dump(dump)
    exclude = set(app.config.get("EXCLUDE_PEERS", []))
    peers = [p for p in peers if p["public_key"] not in exclude]
    return jsonify({"interface": iface, "fetched_at": int(time.time()), "peers": peers})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interface", required=True, help="WireGuard interface (wg0)")
    ap.add_argument("--bind-ip", required=True, help="Bind IP (VPS WireGuard IP, e.g. 192.168.20.2)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--exclude-peer", action="append", default=[])
    args = ap.parse_args()

    token = load_token(args.token_file)
    app.config["API_TOKEN"] = token
    app.config["INTERFACE"] = args.interface
    app.config["EXCLUDE_PEERS"] = args.exclude_peer

    # IMPORTANT: bind only to the WireGuard IP to limit exposure
    print(f"Starting WG publisher on {args.bind_ip}:{args.port} for iface {args.interface}")
    app.run(host=args.bind_ip, port=args.port)
    
if __name__ == "__main__":
    main()

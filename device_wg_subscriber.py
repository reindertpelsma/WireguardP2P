#!/usr/bin/env python3
"""
device_wg_subscriber.py

To establish P2P connections between Remote client and the server even if both are behind firewalls that block inbound connections

Polls the VPS API over the WireGuard tunnel and updates local wg peer endpoints and pka.

Usage example:
  sudo /usr/local/bin/device_wg_subscriber.py \
    --iface wg0 \
    --vps-api http://192.168.20.2:8080/api/peers \
    --token-file /etc/wg-subscriber/token.txt \
    --poll 10 \
    --keepalive 25

Notes:
 - By default the script assumes plain HTTP because traffic is on the WireGuard tunnel.
 - Use --dry-run to preview actions without calling `wg set`.
"""
import argparse
import time
import subprocess
import requests
import random
import json
import sys

def run_wg_show_dump(iface):
    proc = subprocess.run(["wg", "show", iface, "dump"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout

def parse_wg_dump_peers(dump_text):
    lines = [l for l in dump_text.splitlines() if l.strip()]
    if not lines:
        return {}
    peers = {}
    for pline in lines[1:]:
        parts = pline.split()
        if len(parts) < 8:
            continue
        pubkey = parts[0]
        endpoint = parts[2] if parts[2] != '-' else None
        try:
            latest_handshake = int(parts[4])
        except Exception:
            latest_handshake = 0
        try:
            pka = int(parts[7]) if parts[7] != '-' else None
        except Exception:
            pka = None
        peers[pubkey] = {"endpoint": endpoint, "latest_handshake": latest_handshake, "persistent_keepalive": pka}
    return peers

def apply_wg_set(iface, pubkey, endpoint=None, pka=None):
    cmd = ["wg", "set", iface, "peer", pubkey]
    if endpoint is not None:
        cmd += ["endpoint", endpoint]
    if pka is not None:
        if pka == 0:
            cmd += ["persistent-keepalive", "off"]
        else:
            cmd += ["persistent-keepalive", str(pka)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout

def load_token(path):
    with open(path, "r") as fh:
        return fh.read().strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True)
    ap.add_argument("--vps-api", required=True, help="full URL, e.g. http://192.168.20.2:8080/api/peers")
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--poll", type=int, default=10)
    ap.add_argument("--keepalive", type=int, default=25)
    ap.add_argument("--stale-threshold", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = load_token(args.token_file)
    headers = {"Authorization": f"Bearer {token}"}
    last_backoff = 1

    while True:
        # small jitter to avoid perfect sync if many nodes
        time.sleep(random.uniform(0, 0.2))
        try:
            r = requests.get(args.vps_api, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            peers = data.get("peers", [])
            remote_by_pub = {p["public_key"]: p for p in peers}
            last_backoff = 1  # reset backoff on success
        except Exception as e:
            print(f"[{time.asctime()}] fetch error: {e}", file=sys.stderr)
            # Exponential backoff with cap
            time.sleep(min(60, last_backoff))
            last_backoff = min(60, last_backoff * 2)
            continue

        try:
            local_dump = run_wg_show_dump(args.iface)
            local_peers = parse_wg_dump_peers(local_dump)
        except Exception as e:
            print(f"[{time.asctime()}] local wg read error: {e}", file=sys.stderr)
            time.sleep(args.poll)
            continue

        now = int(time.time())

        for pubkey, rpeer in remote_by_pub.items():
            remote_endpoint = rpeer.get("endpoint")
            remote_latest = rpeer.get("latest_handshake", 0)
            online = (remote_latest != 0) and ((now - int(remote_latest)) <= args.stale_threshold)

            local = local_peers.get(pubkey, {})
            local_endpoint = local.get("endpoint")
            local_pka = local.get("persistent_keepalive")

            desired_pka = args.keepalive if online else 0
            need_set_endpoint = (remote_endpoint is not None and remote_endpoint != local_endpoint)
            need_set_pka = ((local_pka or 0) != (desired_pka or 0))

            if need_set_endpoint or need_set_pka:
                print(f"[{time.asctime()}] Update peer {pubkey}: endpoint {local_endpoint} -> {remote_endpoint}, pka {local_pka} -> {desired_pka}")
                if args.dry_run:
                    continue
                try:
                    ep_arg = remote_endpoint if need_set_endpoint else None
                    pka_arg = desired_pka if need_set_pka else None
                    out = apply_wg_set(args.iface, pubkey, endpoint=ep_arg, pka=pka_arg)
                    print(out)
                except Exception as e:
                    print(f"[{time.asctime()}] wg set error for {pubkey}: {e}", file=sys.stderr)

        # Clear pka for local peers not present remotely
        for local_pub, local_meta in local_peers.items():
            if local_pub not in remote_by_pub:
                local_pka = local_meta.get("persistent_keepalive")
                if local_pka and not args.dry_run:
                    print(f"[{time.asctime()}] Clearing pka for unknown remote peer {local_pub}")
                    try:
                        apply_wg_set(args.iface, local_pub, endpoint=None, pka=0)
                    except Exception as e:
                        print(f"[{time.asctime()}] error clearing pka {local_pub}: {e}", file=sys.stderr)

        time.sleep(args.poll)

if __name__ == "__main__":
    main()

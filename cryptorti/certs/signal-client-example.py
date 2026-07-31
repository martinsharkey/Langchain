#!/usr/bin/env python3
"""
Example WebSocket client for connecting to the crypto_rti signal engine.

Usage:
    python signal-client-example.py --host <EC2_PUBLIC_IP> --port 8443 \
        --ca ca.pem --cert client.pem --key client-key.pem

Requires: pip install websockets
"""

import argparse
import asyncio
import json
import ssl

import websockets


async def listen(uri: str, ssl_ctx: ssl.SSLContext):
    async for ws in websockets.connect(uri, ssl=ssl_ctx):
        try:
            print(f"Connected to {uri}")
            async for message in ws:
                if message == "pong":
                    continue
                signal = json.loads(message)
                stage = signal.get("stage", "?")
                signal_id = signal.get("signal_id", "?")
                transfer = signal.get("whale_transfer", {})
                amount = transfer.get("amount_btc", 0)
                exchange = transfer.get("exchange", "?")
                usd = transfer.get("amount_usd", 0)
                print(f"[{stage}] {signal_id}: {amount:.2f} BTC (${usd:,.0f}) -> {exchange}")
                for update in signal.get("updates", []):
                    print(f"  {update['time']} | {update['msg']}")
                print()
        except websockets.ConnectionClosed:
            print("Disconnected. Reconnecting...")
            continue


def main():
    parser = argparse.ArgumentParser(description="Signal engine WebSocket client")
    parser.add_argument("--host", required=True, help="Signal engine host (IP or DNS)")
    parser.add_argument("--port", type=int, default=8443, help="WebSocket port")
    parser.add_argument("--ca", required=True, help="CA certificate file")
    parser.add_argument("--cert", required=True, help="Client certificate file")
    parser.add_argument("--key", required=True, help="Client private key file")
    args = parser.parse_args()

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_ctx.load_cert_chain(certfile=args.cert, keyfile=args.key)
    ssl_ctx.load_verify_locations(cafile=args.ca)
    ssl_ctx.check_hostname = False  # self-signed CA

    uri = f"wss://{args.host}:{args.port}"
    print(f"Connecting to {uri}...")
    asyncio.run(listen(uri, ssl_ctx))


if __name__ == "__main__":
    main()

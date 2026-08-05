"""
scan_plcs.py
------------
Standalone script to discover OPC UA servers (PLCs) on the local network.

Usage:
    python scan_plcs.py                              # auto-detect subnet, default port 4840
    python scan_plcs.py --subnet 192.168.224.0/24     # manual subnet
    python scan_plcs.py --port 4841                   # custom OPC UA port
    python scan_plcs.py --timeout 5                   # custom OPC UA connect timeout

Output:
    - Console table of found servers
    - scan_results.json with the same data, for later use in the
      installation wizard
"""

from __future__ import annotations
import argparse
import asyncio
import ipaddress
import json
import socket
import sys
import time

try:
    from opcua import Client
except ImportError:
    print("Missing dependency. Install it with:\n  pip install opcua --break-system-packages")
    sys.exit(1)


DEFAULT_PORT = 4841   # Opelka B&R PLCs use 4841, not the generic OPC UA default 4840
PORT_SCAN_TIMEOUT = 0.3     # seconds per host, for the fast TCP check
DEFAULT_OPCUA_TIMEOUT = 2.0  # seconds, for the real OPC UA handshake


# ---------------------------------------------------------------------------
# Step 0 — detect local subnet
# ---------------------------------------------------------------------------

def detect_local_subnet() -> str:
    """
    Guess the /24 subnet of the primary network interface by opening
    a dummy UDP socket to a public address (no packets actually sent).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()

    network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    return str(network)


# ---------------------------------------------------------------------------
# Step 1 — fast async TCP port scan
# ---------------------------------------------------------------------------

async def _check_port(ip: str, port: int, timeout: float) -> bool:
    try:
        conn = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def scan_subnet(subnet: str, port: int, timeout: float) -> list[str]:
    network = ipaddress.ip_network(subnet, strict=False)
    hosts = list(network.hosts())
    total = len(hosts)

    open_ips: list[str] = []
    sem = asyncio.Semaphore(200)   # limit concurrent connections

    async def worker(ip: str, index: int):
        async with sem:
            is_open = await _check_port(str(ip), port, timeout)
            if is_open:
                open_ips.append(str(ip))
            if (index + 1) % 25 == 0 or (index + 1) == total:
                print(f"  Scanning... {index + 1}/{total}", end="\r")

    await asyncio.gather(*(worker(ip, i) for i, ip in enumerate(hosts)))
    print(f"  Scanning... {total}/{total} done" + " " * 10)
    return sorted(open_ips, key=lambda x: ipaddress.ip_address(x))


# ---------------------------------------------------------------------------
# Step 2 — confirm real OPC UA servers
# ---------------------------------------------------------------------------

def probe_opcua_server(ip: str, port: int, timeout: float) -> dict:
    url = f"opc.tcp://{ip}:{port}"
    result = {
        "ip": ip,
        "port": port,
        "reachable": False,
        "server_name": "Unknown",
    }

    client = Client(url, timeout=timeout)
    try:
        client.connect()
        result["reachable"] = True

        try:
            endpoints = client.get_endpoints()
            if endpoints:
                app_desc = endpoints[0].Server
                name = getattr(app_desc, "ApplicationName", None)
                if name and getattr(name, "Text", None):
                    result["server_name"] = name.Text
        except Exception:
            pass

    except Exception:
        result["reachable"] = False
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Step 3 — output
# ---------------------------------------------------------------------------

def print_table(results: list[dict]):
    print()
    print(f"{'IP Address':<18} {'Port':<6} {'OPC UA Server':<15} {'Server Name'}")
    print("-" * 70)
    for r in results:
        reachable = "Yes" if r["reachable"] else "No"
        print(f"{r['ip']:<18} {r['port']:<6} {reachable:<15} {r['server_name']}")
    print()


def save_json(results: list[dict], path: str = "scan_results.json"):
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scan local network for OPC UA servers (PLCs)")
    parser.add_argument("--subnet", type=str, default=None,
                         help="Subnet to scan, e.g. 192.168.224.0/24 (default: auto-detect)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                         help=f"OPC UA port to scan for (default: {DEFAULT_PORT})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_OPCUA_TIMEOUT,
                         help="OPC UA connection timeout in seconds (default: 2.0)")
    args = parser.parse_args()

    subnet = args.subnet or detect_local_subnet()
    port = args.port
    print(f"production.pilot — OPC UA Network Scanner")
    print(f"Subnet: {subnet}")
    print(f"Port:   {port}")
    print()

    start = time.time()

    print("Step 1/2 — scanning for open OPC UA ports...")
    open_ips = asyncio.run(scan_subnet(subnet, port, PORT_SCAN_TIMEOUT))

    if not open_ips:
        print()
        print("No OPC UA servers found on this network.")
        print("Check that PLCs are powered on and reachable.")
        save_json([])
        return

    print(f"\nFound {len(open_ips)} host(s) with port {port} open. Verifying...")
    print("Step 2/2 — confirming OPC UA handshake...")

    results = []
    for ip in open_ips:
        print(f"  Checking {ip} ...", end="\r")
        results.append(probe_opcua_server(ip, port, args.timeout))

    print(" " * 40, end="\r")  # clear last line

    elapsed = time.time() - start
    print(f"\nScan complete in {elapsed:.1f}s")

    print_table(results)
    save_json(results)


if __name__ == "__main__":
    main()
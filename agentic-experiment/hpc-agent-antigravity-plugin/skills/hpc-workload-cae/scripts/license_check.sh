#!/usr/bin/env bash
# ISV License Server Network Reachability and Port Probe

set -u

SERVER=""
PORT="1055"
VENDOR_PORT="27000"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) SERVER="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --vendor-port) VENDOR_PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$SERVER" ]; then
    echo "Usage: bash license_check.sh --server <IP_OR_HOSTNAME> [--port 1055] [--vendor-port 27000]"
    exit 1
fi

echo "================================================================="
echo "        Probing ISV License Server: $SERVER                     "
echo "================================================================="

# 1. Test ICMP Ping Latency
echo "[1/3] Testing ICMP Ping..."
if ping -c 3 -W 2 "$SERVER" &>/dev/null; then
    rtt=$(ping -c 3 -W 2 "$SERVER" | tail -n 1 | awk -F '/' '{print $5}')
    echo "  [PASS] Server is reachable via ICMP (Avg RTT: ${rtt} ms)."
else
    echo "  [WARN] Ping failed or ICMP blocked by firewall. Continuing port probe..."
fi

# 2. Test Main License Daemon Port
echo "[2/3] Probing License Manager Port ($PORT)..."
if nc -z -w 3 "$SERVER" "$PORT" &>/dev/null; then
    echo "  [PASS] Port $PORT (Main License Daemon) is OPEN and listening."
else
    echo "  [FAIL] Port $PORT is unreachable. Check VPC firewall or VPN routing."
fi

# 3. Test Vendor Daemon Port
echo "[3/3] Probing Vendor Daemon Port ($VENDOR_PORT)..."
if nc -z -w 3 "$SERVER" "$VENDOR_PORT" &>/dev/null; then
    echo "  [PASS] Port $VENDOR_PORT (Vendor Daemon) is OPEN and listening."
else
    echo "  [INFO] Port $VENDOR_PORT is closed or dynamically assigned. If FlexLM uses dynamic vendor ports, ensure the port range is open."
fi

echo "================================================================="

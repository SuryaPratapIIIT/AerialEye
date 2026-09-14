#!/usr/bin/env python3
"""
AerialEye Hugging Face Backend Keep-Alive Service
--------------------------------------------------
Pings the Hugging Face Space health endpoint periodically to prevent the Docker space
from going into sleep mode.

Usage:
    # Run continuously every 10 minutes (600 seconds)
    python scripts/keep_alive.py

    # Run once (useful for OS crontab or automated jobs)
    python scripts/keep_alive.py --single

    # Custom interval (e.g., every 5 minutes)
    python scripts/keep_alive.py --interval 300

    # Custom URL
    python scripts/keep_alive.py --url https://prfct-suraj-aerialeye-backend.hf.space/api/health
"""

import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request

# Ensure UTF-8 output encoding if possible
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DEFAULT_URL = "https://prfct-suraj-aerialeye-backend.hf.space/api/health"
DEFAULT_INTERVAL = 600  # 10 minutes in seconds


def ping_health(url: str, timeout: int = 30) -> bool:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] Pinging Hugging Face Space: {url} ...")
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AerialEye-KeepAlive/1.0"}
    )
    
    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as response:
            elapsed = time.time() - start_time
            status_code = response.getcode()
            body = response.read().decode("utf-8")
            
            try:
                data = json.loads(body)
                service_status = data.get("status", "unknown")
            except Exception:
                service_status = body[:50]
                
            if status_code == 200:
                print(f"[{timestamp}] [OK] Success (HTTP {status_code}) in {elapsed:.2f}s | Status: {service_status}")
                return True
            else:
                print(f"[{timestamp}] [WARN] Non-200 Response (HTTP {status_code}) in {elapsed:.2f}s")
                return False
    except urllib.error.HTTPError as err:
        print(f"[{timestamp}] [ERROR] HTTP Error {err.code}: {err.reason}")
        return False
    except urllib.error.URLError as err:
        print(f"[{timestamp}] [ERROR] Connection Error: {err.reason}")
        return False
    except Exception as err:
        print(f"[{timestamp}] [ERROR] Unexpected Error: {err}")
        return False


def main():
    parser = argparse.ArgumentParser(description="AerialEye Backend Keep-Alive Pinger")
    parser.add_argument("--url", type=str, default=DEFAULT_URL, help="Health check endpoint URL")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Ping interval in seconds (default: 600)")
    parser.add_argument("--single", action="store_true", help="Run once and exit")
    
    args = parser.parse_args()

    if args.single:
        success = ping_health(args.url)
        sys.exit(0 if success else 1)

    print("==================================================")
    print(" AerialEye HF Backend Keep-Alive Daemon Running   ")
    print(f" Target URL: {args.url}")
    print(f" Interval:   Every {args.interval} seconds ({args.interval // 60} min)")
    print(" Press Ctrl+C to stop.")
    print("==================================================\n")

    while True:
        ping_health(args.url)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

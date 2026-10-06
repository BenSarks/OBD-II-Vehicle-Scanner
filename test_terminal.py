#!/usr/bin/env python3
"""
test_terminal.py
=================

Bare-bones terminal harness for exercising ``obd_backend.OBDBackend``
against a real vehicle - no GUI, just a numbered menu. Meant for
bench-testing the backend before any UI is built on top of it.

Usage:
    python test_terminal.py                       # auto-detect the adapter's port
    python test_terminal.py --port COM5           # Windows, explicit port
    python test_terminal.py --port /dev/ttyUSB0   # Linux, explicit port
    python test_terminal.py --list-ports          # list serial ports and exit

Safety note: menu option 6 (clear trouble codes) resets the MIL and
readiness monitors on the real vehicle. It asks for a typed confirmation
before doing anything.
"""

from __future__ import annotations

import argparse
import sys
import time

from obd_backend import DEFAULT_LIVE_PIDS, OBDBackend, OBDBackendError, available_ports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="No-UI test harness for the OBD-II backend.")
    parser.add_argument("--port", default=None, help="Serial port, e.g. COM5 or /dev/ttyUSB0 (default: auto-detect)")
    parser.add_argument("--baudrate", type=int, default=None, help="Force a baud rate (default: auto)")
    parser.add_argument("--protocol", default=None, help="Force an OBD protocol id, e.g. '6' (default: auto)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-command timeout in seconds (default: 30)")
    parser.add_argument("--list-ports", action="store_true", help="List detected serial ports and exit")
    return parser.parse_args()


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def format_reading(name: str, reading: dict) -> str:
    if not reading["supported"]:
        return f"  {name:<24} not supported by this vehicle"
    if reading["value"] is None:
        return f"  {name:<24} no data"
    unit = f" {reading['unit']}" if reading["unit"] else ""
    return f"  {name:<24} {reading['value']}{unit}"


def show_status(backend: OBDBackend) -> None:
    print_header("Connection status")
    info = backend.connection_info()
    print(f"  Status:        {info['status']}")
    print(f"  Port:          {info['port']}")
    print(f"  Protocol:      {info['protocol_name']} ({info['protocol_id']})")
    print(f"  Car connected: {backend.is_connected()}")


def show_live_data(backend: OBDBackend) -> None:
    print_header("Live data snapshot")
    readings = backend.read_live_data(DEFAULT_LIVE_PIDS)
    for name, reading in readings.items():
        print(format_reading(name, reading))


def stream_live_data(backend: OBDBackend) -> None:
    print_header("Streaming live data (Ctrl+C to stop)")
    try:
        while True:
            readings = backend.read_live_data(DEFAULT_LIVE_PIDS)
            parts = []
            for name, r in readings.items():
                if r["supported"] and r["value"] is not None:
                    parts.append(f"{name}={r['value']}{r['unit'] or ''}")
                else:
                    parts.append(f"{name}=--")
            print(" | ".join(parts))
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopped.")


def show_dtcs(backend: OBDBackend) -> None:
    print_header("Stored trouble codes")
    codes = backend.get_dtcs()
    if not codes:
        print("  No stored trouble codes (or the adapter did not respond).")
        return
    for code, description in codes:
        print(f"  {code}  {description or '(no description available)'}")


def show_freeze_frame(backend: OBDBackend) -> None:
    print_header("Freeze frame data")
    frame = backend.get_freeze_frame()
    if frame["dtc"] is None:
        print("  No freeze frame stored.")
        return
    code, description = frame["dtc"]
    print(f"  Triggering DTC: {code}  {description or '(no description available)'}")
    if not frame["parameters"]:
        print("  (vehicle reported no Mode 02 parameters)")
    for name, reading in frame["parameters"].items():
        unit = f" {reading['unit']}" if reading["unit"] else ""
        value = reading["value"] if reading["value"] is not None else "no data"
        print(f"  {name:<24} {value}{unit}")


def clear_dtcs(backend: OBDBackend) -> None:
    print_header("Clear trouble codes")
    print("  This resets the MIL and readiness monitors on the vehicle.")
    confirm = input("  Type YES to confirm: ").strip()
    if confirm != "YES":
        print("  Cancelled.")
        return
    ok = backend.clear_dtcs()
    print("  Adapter acknowledged the clear command." if ok else "  No response from adapter - clear may have failed.")


MENU = """
1) Connection status
2) Read live data (snapshot)
3) Stream live data (Ctrl+C to stop)
4) Read trouble codes
5) Read freeze frame data
6) Clear trouble codes
7) List supported PIDs
0) Quit
"""


def main() -> int:
    args = parse_args()

    if args.list_ports:
        ports = available_ports()
        print("Detected serial ports:" if ports else "No serial ports detected.")
        for p in ports:
            print(f"  {p}")
        return 0

    print("Connecting to adapter...")
    backend = OBDBackend(
        portstr=args.port,
        baudrate=args.baudrate,
        protocol=args.protocol,
        timeout=args.timeout,
    )
    connected = backend.connect()
    show_status(backend)
    if not connected:
        print(
            "\nCar is not fully connected yet. The menu still works - some "
            "options will just report 'not supported' / no data until the "
            "adapter reaches a live vehicle (ignition on; engine running "
            "helps for RPM and similar PIDs)."
        )

    try:
        while True:
            print(MENU)
            choice = input("Choice: ").strip()
            if choice == "1":
                show_status(backend)
            elif choice == "2":
                show_live_data(backend)
            elif choice == "3":
                stream_live_data(backend)
            elif choice == "4":
                show_dtcs(backend)
            elif choice == "5":
                show_freeze_frame(backend)
            elif choice == "6":
                clear_dtcs(backend)
            elif choice == "7":
                print_header("Supported PIDs")
                for name in backend.list_supported_pids():
                    print(f"  {name}")
            elif choice == "0":
                break
            else:
                print("Unknown choice.")
    except OBDBackendError as exc:
        print(f"Backend error: {exc}")
        return 1
    finally:
        backend.disconnect()
        print("Disconnected.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

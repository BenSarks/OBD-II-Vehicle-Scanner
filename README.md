# Car OBD

OBD-II diagnostic app (Windows + Linux, Python), with a PySide6 desktop
GUI - window titled **Diagnostics** - on top of a UI-agnostic backend
layer.

## Layout

```
obd_backend/
  connection.py   # OBDBackend class: connect, live data, DTCs, freeze frame
  __init__.py     # re-exports the public API
gui.py            # Worker (background QThread) + MainWindow (sidebar nav + pages)
app.py            # GUI entry point - `python app.py`
test_terminal.py  # no-UI menu script for testing against a real vehicle
requirements.txt
```

## Setup

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Finding your adapter's port

- **Windows**: USB and Bluetooth ELM327 adapters show up as a `COMx` port.
  Check Device Manager > Ports (COM & LPT).
- **Linux**: usually `/dev/ttyUSB0` (USB) or `/dev/rfcomm0` (Bluetooth,
  after pairing/binding with `rfcomm`). You may need to be in the
  `dialout` group to access it.

### Bluetooth adapters (e.g. MUCAR BT200)

Bluetooth ELM327 adapters need to be paired with the OS first - once
paired, they show up as a normal serial port, exactly like a USB
adapter, and everything below applies the same way.

1. In the app, click **Pair Bluetooth Device…** (Windows opens the
   Bluetooth settings page for you; on Linux see below).
2. Pair the adapter. If it asks for a PIN, try `1234` or `0000`.
3. Back in the app, click **Refresh Ports** - the adapter's port
   should now be in the list (on Windows it may add two: use the
   "Outgoing" one, not "Incoming").
4. Pick that port and click **Connect**. Leave Baud on Auto.

On Linux there's no in-app pairing helper - pair with `bluetoothctl`,
then bind it to a serial device:

```bash
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF   # the adapter's Bluetooth MAC
```

It'll then show up as `/dev/rfcomm0`.

You can also let python-obd auto-detect the port (leave it unset), or
list what it can see - in the GUI, click **Refresh Ports**; from the
terminal harness:

```bash
python test_terminal.py --list-ports
```

## Running the app

```bash
python app.py
```

Pick a port from the dropdown at the top (or leave it on
**Auto-detect**) and click **Connect**. Baud/Protocol/Timeout and the
Bluetooth pairing helper live on the **Settings** page in the sidebar
- leave them alone unless you know you need them.

The sidebar switches between:

- **Live Data** - a dashboard of stat cards for the key readings
  (RPM, speed, coolant temp, throttle, engine load, fuel level), plus
  a full table of every default PID below; streams every second or
  refreshes on demand with **Snapshot**
- **Trouble Codes** - read stored DTCs; **Clear Trouble Codes…** asks
  for an explicit confirmation first, since it also resets the
  vehicle's readiness monitors
- **Freeze Frame** - the sensor snapshot captured when a DTC was
  first set
- **Supported PIDs** - every Mode 01 PID this vehicle reports as
  supported
- **Settings** - Baud/Protocol/Timeout and Bluetooth pairing; always
  available, even before you connect

All serial I/O runs on a background thread, so the window stays
responsive even while waiting on the adapter.

Click **Dark Mode** / **Light Mode** (bottom of the sidebar) to switch
themes - your choice is remembered between runs.

## Testing against a real vehicle (no-UI harness)

With the adapter plugged in and the ignition on (engine running gives
you RPM, speed, etc.):

```bash
python test_terminal.py --port COM5
```

This gives you a plain numbered menu (connection status, live data
snapshot/stream, read DTCs, read freeze frame, clear DTCs, list supported
PIDs) with no UI framework involved - just to confirm the backend talks
to your hardware before any interface is built on top of it.

**Clearing trouble codes (menu option 6) also resets the vehicle's
readiness monitors** - it asks for a typed `YES` confirmation before
doing anything.

## Backend API

```python
from obd_backend import OBDBackend

backend = OBDBackend(portstr="COM5")   # or None to auto-detect
if backend.connect():
    print(backend.read_live_data())     # dict of PID -> {value, unit, ...}
    print(backend.get_dtcs())           # [(code, description), ...]
    print(backend.get_freeze_frame())   # {"dtc": ..., "parameters": {...}}
    backend.clear_dtcs()                # returns True/False
backend.disconnect()
```

See the docstrings in [obd_backend/connection.py](obd_backend/connection.py)
for the full method list and return shapes.

"""
obd_backend.connection
=======================

Backend layer for talking to an ELM327-compatible OBD-II adapter via the
`python-obd` library (PyPI/pip package name: ``obd``; ``import obd``).

This module has no UI code in it at all. It exposes one class,
``OBDBackend``, with plain functions for:

  * connecting / disconnecting from the adapter
  * reading a snapshot of live sensor data (Mode 01 PIDs)
  * reading and clearing stored trouble codes (Modes 03 / 04)
  * reading freeze frame data (Mode 02 - the sensor snapshot the ECU
    captured at the moment a DTC was first set)

Everything is returned as plain Python data (dict / list / tuple / str /
int / float / bool / None) so a future UI layer (CLI, Qt, web, ...) never
has to import ``obd`` itself or know about its internal types
(OBDCommand, OBDResponse, pint Quantities, ...).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

import obd
from obd import OBDStatus

logger = logging.getLogger(__name__)


class OBDBackendError(Exception):
    """Raised for backend usage errors (e.g. calling a query before connect())."""


# A reasonable default set of Mode 01 PIDs for a live-data view. All of
# these are common, single-frame, "fast" PIDs supported by most OBD-II
# vehicles built after ~2008. Vehicles that don't support a given PID
# just come back with supported=False - see read_live_data().
DEFAULT_LIVE_PIDS: tuple[str, ...] = (
    "RPM",
    "SPEED",
    "COOLANT_TEMP",
    "ENGINE_LOAD",
    "THROTTLE_POS",
    "INTAKE_TEMP",
    "INTAKE_PRESSURE",
    "MAF",
    "FUEL_LEVEL",
    "TIMING_ADVANCE",
    "SHORT_FUEL_TRIM_1",
    "LONG_FUEL_TRIM_1",
    "CONTROL_MODULE_VOLTAGE",
)


@dataclass
class PidReading:
    """A single decoded value coming back from the adapter for one PID."""

    name: str
    description: str
    supported: bool
    value: object = None
    unit: Optional[str] = None
    raw: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "supported": self.supported,
            "value": self.value,
            "unit": self.unit,
            "raw": self.raw,
        }


def available_ports() -> list[str]:
    """
    List serial ports python-obd can see on this machine (COM3, COM4, ...
    on Windows; /dev/ttyUSB0, /dev/rfcomm0, ... on Linux). Handy for
    letting a user pick a port instead of relying on auto-detect.
    """
    return obd.scan_serial()


def _decompose(value):
    """
    Split a python-obd response value into a plain (value, unit) pair.

    Most Mode 01/02 values come back as a pint ``Quantity`` (magnitude +
    units attached, e.g. 725 rpm). We unwrap that into a plain number and
    a unit string so callers never need to import ``obd`` or ``pint``.
    Anything else (e.g. a plain string) is passed through unchanged with
    no unit.
    """
    if value is None:
        return None, None
    if isinstance(value, obd.Unit.Quantity):
        magnitude = value.magnitude
        if isinstance(magnitude, float) and magnitude.is_integer():
            magnitude = int(magnitude)
        return magnitude, str(value.units)
    return value, None


class OBDBackend:
    """
    Thin, UI-agnostic wrapper around python-obd's ``obd.OBD`` connection.

    Typical usage::

        backend = OBDBackend(portstr="COM5")   # or None to auto-detect
        if backend.connect():
            print(backend.read_live_data())
            print(backend.get_dtcs())
        backend.disconnect()

    Or as a context manager::

        with OBDBackend() as backend:
            print(backend.read_live_data())
    """

    def __init__(
        self,
        portstr: Optional[str] = None,
        baudrate: Optional[int] = None,
        protocol: Optional[str] = None,
        fast: bool = True,
        timeout: float = 30.0,
    ):
        """
        Parameters mirror ``obd.OBD()``:

        portstr:  e.g. "COM5" on Windows or "/dev/ttyUSB0" on Linux.
                  Leave as None to let python-obd scan for a serial port
                  (this also covers USB and Bluetooth ELM327 adapters,
                  since both show up as a serial device to the OS).
        baudrate: Leave as None to auto-negotiate (recommended).
        protocol: Leave as None to auto-detect the vehicle's OBD protocol
                  (e.g. "6" for ISO 15765-4 CAN 11-bit/500kbps).
        fast:     Enables python-obd's command optimizations. Keep True
                  unless you're debugging a flaky adapter.
        timeout:  Seconds to wait for the adapter to respond per command.
        """
        self._portstr = portstr
        self._baudrate = baudrate
        self._protocol = protocol
        self._fast = fast
        self._timeout = timeout
        self._connection: Optional[obd.OBD] = None

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        """
        Open the connection to the adapter and negotiate with the vehicle.

        Returns True only if the vehicle's ECU is actually responding
        (status == "Car Connected"). Returns False for any lesser state
        (no adapter found, adapter found but car not responding, etc.)
        rather than raising - call status() / connection_info() to see why.
        """
        self._connection = obd.OBD(
            portstr=self._portstr,
            baudrate=self._baudrate,
            protocol=self._protocol,
            fast=self._fast,
            timeout=self._timeout,
        )
        return self.is_connected()

    def disconnect(self) -> None:
        """Close the serial connection, if one is open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def is_connected(self) -> bool:
        """True only when the ELM327 adapter *and* the vehicle ECU are responding."""
        return self._connection is not None and self._connection.is_connected()

    def status(self) -> str:
        """
        Raw python-obd status string, one of:
          "Not Connected", "ELM Connected", "OBD Connected", "Car Connected"

        Useful for telling a user *why* a connection isn't fully up yet -
        e.g. "ELM Connected" usually means the adapter was found but the
        vehicle ignition is off / out of range.
        """
        if self._connection is None:
            return OBDStatus.NOT_CONNECTED
        return self._connection.status()

    def connection_info(self) -> dict:
        """Small dict describing the active connection, for display/logging."""
        if self._connection is None:
            return {
                "port": None,
                "protocol_name": None,
                "protocol_id": None,
                "status": OBDStatus.NOT_CONNECTED,
            }
        return {
            "port": self._connection.port_name(),
            "protocol_name": self._connection.protocol_name(),
            "protocol_id": self._connection.protocol_id(),
            "status": self._connection.status(),
        }

    def list_supported_pids(self) -> list[str]:
        """Names of every Mode 01 (live data) PID this vehicle reports as supported."""
        self._require_connection()
        return sorted(cmd.name for cmd in self._connection.supported_commands if cmd.mode == 1)

    # ------------------------------------------------------------------ #
    # Live data (Mode 01)
    # ------------------------------------------------------------------ #

    def read_live_data(self, pids: Optional[Iterable[str]] = None) -> dict[str, dict]:
        """
        Query a snapshot of live sensor PIDs.

        pids: iterable of python-obd command names (e.g. "RPM", "SPEED").
              Defaults to DEFAULT_LIVE_PIDS. An unknown name is reported
              back with supported=False instead of raising, so one bad
              name in a caller-supplied list can't blow up the whole read.

        Returns {pid_name: {"description", "supported", "value", "unit", "raw"}}
        """
        self._require_connection()
        names = list(pids) if pids is not None else list(DEFAULT_LIVE_PIDS)
        return {name: self._read_single_pid(name).as_dict() for name in names}

    def read_pid(self, name: str) -> dict:
        """Query a single named PID (e.g. "RPM") and return its reading as a dict."""
        self._require_connection()
        return self._read_single_pid(name).as_dict()

    def _read_single_pid(self, name: str) -> PidReading:
        if not obd.commands.has_name(name):
            return PidReading(name=name, description="Unknown command", supported=False)

        cmd = obd.commands[name]
        if not self._connection.supports(cmd):
            return PidReading(name=name, description=cmd.desc, supported=False)

        response = self._connection.query(cmd)
        if response.is_null():
            return PidReading(name=name, description=cmd.desc, supported=True, value=None)

        value, unit = _decompose(response.value)
        return PidReading(
            name=name,
            description=cmd.desc,
            supported=True,
            value=value,
            unit=unit,
            raw=str(response.value),
        )

    # ------------------------------------------------------------------ #
    # Trouble codes (Modes 03 / 04)
    # ------------------------------------------------------------------ #

    def get_dtcs(self) -> list[tuple[str, str]]:
        """
        Read stored (confirmed) diagnostic trouble codes.

        Returns a list of (code, description) tuples, e.g.
        [("P0301", "Cylinder 1 Misfire Detected")]. An empty list means
        either no codes are stored, or the adapter didn't respond at all -
        check is_connected() beforehand to tell the two apart.
        """
        self._require_connection()
        response = self._connection.query(obd.commands.GET_DTC)
        if not response.messages:
            return []
        return response.value

    def clear_dtcs(self) -> bool:
        """
        Send Mode 04 (clear trouble codes / turn off the MIL).

        WARNING: this also erases freeze frame data and resets the
        vehicle's readiness monitors. Don't call it without confirming
        with the user first.

        python-obd's CLEAR_DTC decoder always reports the response
        *value* as None (there is nothing to decode in an ack), so
        success can't be judged with response.is_null() - it would
        always say "null". Instead we check whether the adapter sent
        back any response frame at all.
        """
        self._require_connection()
        response = self._connection.query(obd.commands.CLEAR_DTC)
        return bool(response.messages)

    # ------------------------------------------------------------------ #
    # Freeze frame (Mode 02)
    # ------------------------------------------------------------------ #

    def get_freeze_frame(self) -> dict:
        """
        Read freeze frame data: the snapshot of sensor values the ECU
        captured at the moment a DTC was first set.

        Returns:
            {
              "dtc": (code, description) or None,
              "parameters": {pid_name: {"description", "value", "unit", "raw"}},
            }

        "dtc" is None when no freeze frame is currently stored (e.g. no
        active codes, or codes were recently cleared). "parameters" only
        contains PIDs the vehicle actually reports as supported in
        Mode 02, which varies a lot by make/model.
        """
        self._require_connection()

        dtc_response = self._connection.query(obd.commands.FREEZE_DTC)
        if not dtc_response.messages:
            # Adapter didn't answer at all - nothing useful to report.
            return {"dtc": None, "parameters": {}}

        frame_dtc = dtc_response.value  # (code, description) tuple, or None

        parameters: dict[str, dict] = {}
        if frame_dtc is not None:
            mode2_cmds = sorted(
                (c for c in self._connection.supported_commands if c.mode == 2),
                key=lambda c: c.name,
            )
            for cmd in mode2_cmds:
                response = self._connection.query(cmd)
                if response.is_null():
                    continue
                value, unit = _decompose(response.value)
                # python-obd names mode 2 PIDs "DTC_<mode 1 name>" - strip
                # that prefix so keys line up with read_live_data() names.
                clean_name = cmd.name[len("DTC_"):] if cmd.name.startswith("DTC_") else cmd.name
                parameters[clean_name] = {
                    "description": cmd.desc,
                    "value": value,
                    "unit": unit,
                    "raw": str(response.value),
                }

        return {"dtc": frame_dtc, "parameters": parameters}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _require_connection(self) -> None:
        if self._connection is None:
            raise OBDBackendError("Not connected - call connect() first.")

    def __enter__(self) -> "OBDBackend":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

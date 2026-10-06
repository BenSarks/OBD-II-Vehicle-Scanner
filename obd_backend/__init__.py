"""
obd_backend
===========

UI-agnostic backend for talking to an ELM327-compatible OBD-II adapter,
built on top of the `python-obd` library (import name: ``obd``).

Everything a future UI layer needs is exposed here; nothing in this
package prints, prompts, or otherwise assumes a particular front end.
"""

from .connection import (
    DEFAULT_LIVE_PIDS,
    OBDBackend,
    OBDBackendError,
    PidReading,
    available_ports,
)

__all__ = [
    "OBDBackend",
    "OBDBackendError",
    "PidReading",
    "DEFAULT_LIVE_PIDS",
    "available_ports",
]

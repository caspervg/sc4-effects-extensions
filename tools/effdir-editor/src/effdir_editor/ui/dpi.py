"""Windows DPI setup and small helpers used by the wxPython UI.

The editor is normally launched by ``python.exe`` (or a console-script
shim), so there is no application manifest of our own to declare DPI
awareness.  Set the process awareness before importing wxPython instead.
"""

from __future__ import annotations

import ctypes
import sys


# Windows 10's per-monitor-v2 awareness context.  Keep this as a numeric
# constant so importing this module does not require Windows-only headers.
_PER_MONITOR_AWARE_V2 = -4


def enable_windows_dpi_awareness() -> None:
    """Make the current process per-monitor DPI aware when running on Windows.

    ``SetProcessDpiAwarenessContext`` is preferred because it enables the
    behavior needed when the window moves between monitors with different
    scale factors.  The older APIs are retained as fallbacks for older
    Windows versions and are intentionally best-effort: the process may
    already have inherited an awareness setting from its host.
    """

    if sys.platform != "win32":
        return

    try:
        user32 = ctypes.windll.user32
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_bool
        if set_context(ctypes.c_void_p(_PER_MONITOR_AWARE_V2)):
            return
    except (AttributeError, OSError, ctypes.ArgumentError, OverflowError):
        pass

    try:
        shcore = ctypes.windll.shcore
        set_awareness = shcore.SetProcessDpiAwareness
        set_awareness.argtypes = [ctypes.c_int]
        set_awareness.restype = ctypes.c_long
        # PROCESS_PER_MONITOR_DPI_AWARE
        if set_awareness(2) == 0:
            return
    except (AttributeError, OSError, ctypes.ArgumentError, OverflowError):
        pass

    try:
        # Last resort for pre-Windows 10 systems.  This is system-DPI aware,
        # but still avoids Windows bitmap virtualization and blurry controls.
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError, ctypes.ArgumentError):
        pass

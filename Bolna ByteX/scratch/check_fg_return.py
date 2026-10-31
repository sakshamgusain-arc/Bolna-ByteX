import subprocess
import time
import ctypes
from ctypes import wintypes, byref, c_ulong, create_unicode_buffer
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

p = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)

real_hwnd = None
def enum_cb(h, lp):
    global real_hwnd
    if user32.IsWindowVisible(h):
        length = user32.GetWindowTextLengthW(h)
        if length > 0:
            tbuf = create_unicode_buffer(length + 1)
            user32.GetWindowTextW(h, tbuf, length + 1)
            title = tbuf.value.lower()
            if "notepad" in title and title != "popuphost":
                real_hwnd = h
    return True
WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows(WNDENUM(enum_cb), 0)

print(f"Target real_hwnd: {real_hwnd}")
print(f"Foreground window before: {user32.GetForegroundWindow()}")

ret_sf = user32.SetForegroundWindow(real_hwnd)
print(f"SetForegroundWindow returned: {ret_sf}")
print(f"Foreground window after: {user32.GetForegroundWindow()}")

p.terminate()


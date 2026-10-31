import subprocess
import time
import ctypes
from ctypes import wintypes, byref
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

user32 = ctypes.windll.user32
p = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)
hwnd = user32.FindWindowW('Notepad', None)

# Check current foreground window
fg_before = user32.GetForegroundWindow()
print(f'Foreground before focus: {fg_before}, Notepad HWND: {hwnd}')

# Test 1: Send text without bringing to foreground or clicking
from services.input_controller import input_controller
input_controller.type_unicode_text('TEST_WITHOUT_FOCUS ')
time.sleep(0.5)

# Test 2: Now bring to foreground
from security.permissions import SecurityPermissions
SecurityPermissions.verify_application_window('notepad')
time.sleep(0.5)

fg_after = user32.GetForegroundWindow()
print(f'Foreground after verify_application_window: {fg_after} (matches Notepad: {fg_after == hwnd})')

# Click inside Notepad client area (e.g. center of window)
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
rect = RECT()
user32.GetWindowRect(hwnd, byref(rect))
cx = (rect.left + rect.right) // 2
cy = (rect.top + rect.bottom) // 2
print(f'Window rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}), Center: ({cx}, {cy})')

user32.SetCursorPos(cx, cy)
user32.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.05)
user32.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.2)

input_controller.type_unicode_text('HELLO_FOCUSED_NOTEPAD')
time.sleep(0.5)

# Check what text is in RichEdit
rich_hwnd = None
def cb(h, lp):
    global rich_hwnd
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    if buf.value == 'RichEditD2DPT':
        rich_hwnd = h
    return True
WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumChildWindows(hwnd, WNDENUM(cb), 0)

WM_GETTEXT = 0x000D
buf = ctypes.create_unicode_buffer(512)
user32.SendMessageW(rich_hwnd, WM_GETTEXT, 512, buf)
print(f'Extracted text from RichEdit: "{buf.value}"')

p.terminate()

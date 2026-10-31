import subprocess
import time
import ctypes
from ctypes import wintypes, byref, c_ulong, Structure

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class RECT(Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]

# Launch Notepad
p = subprocess.Popen(['notepad.exe'])
time.sleep(1.0)

# Find top-level Notepad window
hwnd = user32.FindWindowW('Notepad', None)
print(f"Top-level Notepad HWND: {hwnd}")

# Proper Windows Foreground Activation Protocol:
def force_foreground(target_hwnd):
    # 1. Restore if minimized
    if user32.IsIconic(target_hwnd):
        user32.ShowWindow(target_hwnd, 9) # SW_RESTORE
    else:
        user32.ShowWindow(target_hwnd, 5) # SW_SHOW

    fg_hwnd = user32.GetForegroundWindow()
    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
    tgt_tid = user32.GetWindowThreadProcessId(target_hwnd, None)

    # Attach thread input to bypass Windows LockSetForegroundWindow
    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
    if tgt_tid and tgt_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, tgt_tid, True)

    # Simulate Alt key tap
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)

    # Bring to foreground
    user32.BringWindowToTop(target_hwnd)
    user32.SetForegroundWindow(target_hwnd)
    user32.SetActiveWindow(target_hwnd)
    user32.SwitchToThisWindow(target_hwnd, True)

    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    if tgt_tid and tgt_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, tgt_tid, False)

force_foreground(hwnd)
time.sleep(0.3)

fg_now = user32.GetForegroundWindow()
print(f"Foreground window is now: {fg_now} (Matches Notepad: {fg_now == hwnd})")

# Find RichEdit control
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
print(f"RichEdit HWND: {rich_hwnd}")

# Click inside the RichEdit control to set keyboard focus
rect = RECT()
user32.GetWindowRect(rich_hwnd if rich_hwnd else hwnd, byref(rect))
cx = (rect.left + rect.right) // 2
cy = (rect.top + rect.bottom) // 2
print(f"Clicking at ({cx}, {cy}) inside edit area...")

user32.SetCursorPos(cx, cy)
time.sleep(0.05)
user32.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.04)
user32.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.15)

# Type Unicode text
test_text = "Hello I am Negasaurus."
for ch in test_text:
    code = ord(ch)
    # KEYBDINPUT: type=1, dwFlags=4 (UNICODE)
    # Use SendInput or SendMessage or input_controller
    pass

import sys
backend_dir = r"c:\Users\ryzzn\OneDrive\Desktop\ByteX Core\backend"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
from services.input_controller import input_controller

input_controller.type_unicode_text(test_text)
time.sleep(0.5)

# Read text from RichEdit via WM_GETTEXT
buf = ctypes.create_unicode_buffer(512)
user32.SendMessageW(rich_hwnd, 0x000D, 512, buf)
print(f"VERIFIED TEXT IN NOTEPAD: '{buf.value}'")

# Also check Image difference
p.terminate()


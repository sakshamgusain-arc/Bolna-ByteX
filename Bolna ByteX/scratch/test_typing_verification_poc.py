import subprocess
import time
import ctypes
from ctypes import wintypes, byref, Structure, c_ulong, create_unicode_buffer
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
from security.permissions import RECT

# Find the REAL Notepad main window:
def find_real_notepad_window():
    real_hwnd = None
    max_area = 0
    def enum_cb(h, lp):
        nonlocal real_hwnd, max_area
        if user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                tbuf = create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, tbuf, length + 1)
                title = tbuf.value.lower()
                cbuf = create_unicode_buffer(256)
                user32.GetClassNameW(h, cbuf, 256)
                cls_name = cbuf.value.lower()
                
                # Check for Notepad process
                pid = c_ulong()
                user32.GetWindowThreadProcessId(h, byref(pid))
                
                if ("notepad" in title or "notepad" in cls_name) and title != "popuphost":
                    r = RECT()
                    user32.GetWindowRect(h, byref(r))
                    area = (r.right - r.left) * (r.bottom - r.top)
                    if area > max_area and area > 10000:
                        max_area = area
                        real_hwnd = h
        return True

    WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUM(enum_cb), 0)
    return real_hwnd

# 1. Start clean Notepad
p = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)

hwnd = find_real_notepad_window()
tbuf = create_unicode_buffer(256)
user32.GetWindowTextW(hwnd, tbuf, 256)
print(f"Found Real Notepad HWND: {hwnd}, Title: '{tbuf.value}'")

# 2. Activate it using AttachThreadInput and SetForegroundWindow
from services.input_controller import input_controller

h_in, old_d = input_controller._attach_desktop_context()
try:
    cur_tid = kernel32.GetCurrentThreadId()
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)

    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
    if tgt_tid and tgt_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, tgt_tid, True)

    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)

    user32.ShowWindow(hwnd, 9) # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetActiveWindow(hwnd)
    user32.SwitchToThisWindow(hwnd, True)

    if fg_tid and fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    if tgt_tid and tgt_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, tgt_tid, False)

    # Click in the document editing area (e.g. center of the window)
    r = RECT()
    user32.GetWindowRect(hwnd, byref(r))
    cx = (r.left + r.right) // 2
    cy = (r.top + r.bottom) // 2
    print(f"Clicking at ({cx}, {cy}) inside document body...")
    user32.SetCursorPos(cx, cy)
    time.sleep(0.06)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.2)
finally:
    input_controller._detach_desktop_context(h_in, old_d)

# 3. Type text
text_to_type = "Hello I am Negasaurus."
input_controller.type_unicode_text(text_to_type)
time.sleep(0.6)

# 4. Check RichEdit text
def read_rich_edit(target_h):
    result = ""
    def cb(ch, lp):
        nonlocal result
        cbuf = create_unicode_buffer(256)
        user32.GetClassNameW(ch, cbuf, 256)
        if cbuf.value in ["RichEditD2DPT", "Edit", "NotepadTextBox"]:
            length = user32.SendMessageW(ch, 0x000E, 0, 0)
            if length > 0:
                tbuf = create_unicode_buffer(length + 2)
                user32.SendMessageW(ch, 0x000D, length + 1, tbuf)
                result = tbuf.value
        return True
    WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumChildWindows(target_h, WNDENUM(cb), 0)
    return result

content = read_rich_edit(hwnd)
print(f"Extracted Content: '{content}'")
assert "Negasaurus" in content, f"Expected Negasaurus in '{content}'"
print("SUCCESSFULLY ENTERED AND VERIFIED TEXT IN NOTEPAD!")

p.terminate()

import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

import ctypes
from ctypes import wintypes, create_unicode_buffer, byref, c_ulong
import psutil
from security.permissions import RECT, SecurityPermissions

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

print("=== REAL RUNTIME WINDOWS DIAGNOSTIC ===")

# 1. Foreground Window
fg_hwnd = user32.GetForegroundWindow()
fg_pid = c_ulong()
fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, byref(fg_pid))
buf_title = create_unicode_buffer(512)
user32.GetWindowTextW(fg_hwnd, buf_title, 512)
buf_cls = create_unicode_buffer(256)
user32.GetClassNameW(fg_hwnd, buf_cls, 256)
fg_proc_name = ""
try:
    fg_proc_name = psutil.Process(fg_pid.value).name()
except Exception:
    pass
print(f"Current Foreground Window: HWND={fg_hwnd}, TID={fg_tid}, PID={fg_pid.value} ({fg_proc_name}), Class='{buf_cls.value}', Title='{buf_title.value}'")

# 2. Open Desktop Context
h_input = user32.OpenInputDesktop(0, False, 0x01FF)
cur_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
print(f"Desktop Context: OpenInputDesktop={h_input}, CurrentThreadDesktop={cur_desk}")
if h_input:
    user32.CloseDesktop(h_input)

# 3. All Notepad Windows
notepad_procs = []
for p in psutil.process_iter(['pid', 'name']):
    if 'notepad' in p.info['name'].lower():
        notepad_procs.append((p.info['pid'], p.info['name']))
print(f"Running Notepad Processes: {notepad_procs}")

# Enumerate all top-level windows matching notepad or notepad process
notepad_windows = []
def enum_cb(h, _):
    if user32.IsWindowVisible(h):
        pid = c_ulong()
        tid = user32.GetWindowThreadProcessId(h, byref(pid))
        pname = ""
        try:
            pname = psutil.Process(pid.value).name().lower()
        except Exception:
            pass
        tbuf = create_unicode_buffer(512)
        user32.GetWindowTextW(h, tbuf, 512)
        cbuf = create_unicode_buffer(256)
        user32.GetClassNameW(h, cbuf, 256)
        title = tbuf.value
        clsname = cbuf.value
        if 'notepad' in pname or 'notepad' in title.lower() or 'notepad' in clsname.lower():
            rect = RECT()
            user32.GetWindowRect(h, byref(rect))
            w = rect.right - rect.left
            h_len = rect.bottom - rect.top
            notepad_windows.append({
                "hwnd": h, "tid": tid, "pid": pid.value, "pname": pname,
                "title": title, "class": clsname,
                "rect": (rect.left, rect.top, rect.right, rect.bottom),
                "dims": (w, h_len),
                "minimized": bool(user32.IsIconic(h))
            })
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

print(f"Visible Notepad Windows Found: {len(notepad_windows)}")
for w in notepad_windows:
    print(f"  HWND={w['hwnd']}, PID={w['pid']} ({w['pname']}), Class='{w['class']}', Title='{w['title']}', Dims={w['dims']}, Minimized={w['minimized']}")

# 4. Check verify_application_window result
win_res = SecurityPermissions.verify_application_window("notepad")
print(f"SecurityPermissions.verify_application_window('notepad') -> {win_res}")


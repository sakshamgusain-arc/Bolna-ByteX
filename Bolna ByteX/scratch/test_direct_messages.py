import subprocess
import time
import ctypes
from ctypes import wintypes, byref, create_unicode_buffer

user32 = ctypes.windll.user32

p = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)

hwnd = user32.FindWindowW('Notepad', None)

rich_hwnd = None
def find_rich(ch, lp):
    global rich_hwnd
    cbuf = create_unicode_buffer(256)
    user32.GetClassNameW(ch, cbuf, 256)
    if cbuf.value in ["RichEditD2DPT", "Edit", "NotepadTextBox"]:
        rich_hwnd = ch
    return True

WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumChildWindows(hwnd, WNDENUM(find_rich), 0)

print(f"Notepad HWND: {hwnd}, RichEdit HWND: {rich_hwnd}")

# Test A: SendMessage WM_SETTEXT directly to RichEditD2DPT
WM_SETTEXT = 0x000C
ret_st = user32.SendMessageW(rich_hwnd, WM_SETTEXT, 0, "Hello I am Negasaurus.")
print(f"WM_SETTEXT returned: {ret_st}")

# Check WM_GETTEXT
tbuf = create_unicode_buffer(512)
ret_gt = user32.SendMessageW(rich_hwnd, 0x000D, 512, tbuf)
print(f"WM_GETTEXT returned {ret_gt}: '{tbuf.value}'")

# Also test EM_REPLACESEL
EM_REPLACESEL = 0x00C2
ret_rep = user32.SendMessageW(rich_hwnd, EM_REPLACESEL, True, " (Appended via EM_REPLACESEL)")
print(f"EM_REPLACESEL returned: {ret_rep}")

ret_gt2 = user32.SendMessageW(rich_hwnd, 0x000D, 512, tbuf)
print(f"WM_GETTEXT after EM_REPLACESEL returned {ret_gt2}: '{tbuf.value}'")

p.terminate()


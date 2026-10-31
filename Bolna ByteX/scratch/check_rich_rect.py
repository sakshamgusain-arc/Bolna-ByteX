import subprocess
import time
import ctypes
from ctypes import wintypes, byref, c_ulong, create_unicode_buffer

user32 = ctypes.windll.user32

p = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)

hwnd = user32.FindWindowW('Notepad', None)

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]

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

r_main = RECT()
user32.GetWindowRect(hwnd, byref(r_main))
print(f"Notepad main rect: left={r_main.left}, top={r_main.top}, right={r_main.right}, bottom={r_main.bottom}")

r_rich = RECT()
user32.GetWindowRect(rich_hwnd, byref(r_rich))
print(f"RichEdit rect: left={r_rich.left}, top={r_rich.top}, right={r_rich.right}, bottom={r_rich.bottom}")

p.terminate()


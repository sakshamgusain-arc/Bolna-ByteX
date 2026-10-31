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
from security.permissions import RECT
from services.screenshot_helper import capture_desktop
from services.input_controller import input_controller

# 1. Start clean Notepad
p = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)

# Find Real Notepad Window
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

# Capture pre-screenshot
pre_img = "scratch/pre_notepad.png"
post_img = "scratch/post_notepad.png"
capture_desktop(pre_img)

# Foreground activation
user32.ShowWindow(real_hwnd, 9)
user32.SetForegroundWindow(real_hwnd)
user32.BringWindowToTop(real_hwnd)

# Click center of Notepad
r = RECT()
user32.GetWindowRect(real_hwnd, byref(r))
cx = (r.left + r.right) // 2
cy = (r.top + r.bottom) // 2

user32.SetCursorPos(cx, cy)
time.sleep(0.05)
user32.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.05)
user32.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.15)

# Type text
input_controller.type_unicode_text("Hello I am Negasaurus.")
time.sleep(0.5)

# Capture post-screenshot
capture_desktop(post_img)

# Compute diff
from services.visual_verifier import visual_verifier
diff = visual_verifier.compute_image_diff_metric(pre_img, post_img)
print(f"Image diff metric: {diff}")

# Also OCR
from services.ocr_service import ocr_service
import asyncio

async def test_ocr():
    res = await ocr_service.extract_text(post_img)
    print(f"OCR Full Text: {res.get('full_text')}")

asyncio.run(test_ocr())

p.terminate()

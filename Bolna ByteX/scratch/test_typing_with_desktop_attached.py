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
from services.input_controller import input_controller

# 1. Attach desktop context FIRST
h_in, old_d = input_controller._attach_desktop_context()
print(f"Attached to desktop context: {h_in}")

try:
    # 2. Launch Notepad
    p = subprocess.Popen(['notepad.exe'])
    time.sleep(1.2)

    # Find Notepad window on interactive desktop
    real_hwnd = None
    def enum_cb(h, lp):
        global real_hwnd
        if user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                tbuf = create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, tbuf, length + 1)
                title = tbuf.value.lower()
                cbuf = create_unicode_buffer(256)
                user32.GetClassNameW(h, cbuf, 256)
                cls_name = cbuf.value.lower()
                if "notepad" in title and title != "popuphost" and cls_name == "notepad":
                    real_hwnd = h
        return True

    WNDENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumDesktopWindows(h_in, WNDENUM(enum_cb), 0)
    print(f"Found Notepad window: HWND {real_hwnd}")

    # 3. Bring to foreground on interactive desktop
    user32.ShowWindow(real_hwnd, 9) # SW_RESTORE
    user32.BringWindowToTop(real_hwnd)
    
    # Bypass foreground lock via Alt key
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    ret_sf = user32.SetForegroundWindow(real_hwnd)
    user32.SetActiveWindow(real_hwnd)
    print(f"SetForegroundWindow returned: {ret_sf}, Foreground now: {user32.GetForegroundWindow()}")

    # 4. Click inside Notepad text area
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
    r = RECT()
    user32.GetWindowRect(real_hwnd, byref(r))
    cx = (r.left + r.right) // 2
    cy = (r.top + r.bottom) // 2
    print(f"Notepad rect: ({r.left}, {r.top}, {r.right}, {r.bottom}), Center: ({cx}, {cy})")

    user32.SetCursorPos(cx, cy)
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.15)

    # 5. Type text
    text_to_type = "Hello I am Negasaurus."
    input_controller.type_unicode_text(text_to_type)
    time.sleep(0.5)

    # 6. Read text from RichEdit
    rich_hwnd = None
    def find_rich(ch, lp):
        global rich_hwnd
        cbuf = create_unicode_buffer(256)
        user32.GetClassNameW(ch, cbuf, 256)
        if cbuf.value in ["RichEditD2DPT", "Edit", "NotepadTextBox"]:
            rich_hwnd = ch
        return True
    user32.EnumChildWindows(real_hwnd, WNDENUM(find_rich), 0)
    print(f"RichEdit HWND: {rich_hwnd}")

    tbuf = create_unicode_buffer(512)
    user32.SendMessageW(rich_hwnd, 0x000D, 512, tbuf)
    print(f"Extracted RichEdit text: '{tbuf.value}'")

    # Also capture screenshot and check diff or ocr
    from services.screenshot_helper import capture_desktop
    from services.ocr_service import ocr_service
    import asyncio
    capture_desktop("scratch/notepad_typed.png")
    
    async def do_ocr():
        res = await ocr_service.extract_text("scratch/notepad_typed.png")
        print(f"OCR text found: '{res.get('full_text')}'")
    asyncio.run(do_ocr())

finally:
    input_controller._detach_desktop_context(h_in, old_d)
    p.terminate()


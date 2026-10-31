import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
import subprocess, time, ctypes
from ctypes import wintypes, create_unicode_buffer, c_ulong, byref
from security.permissions import RECT
from services.input_controller import input_controller
from services.screenshot_helper import capture_desktop
from services.ocr_service import ocr_service
import asyncio

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

proc = subprocess.Popen(['notepad.exe'])
time.sleep(1.0)

try:
    found_windows = []
    def enum_cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                t_lower = title.lower()
                if 'notepad' in t_lower and 'popuphost' not in t_lower:
                    rect = RECT()
                    user32.GetWindowRect(hwnd, byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w >= 200 and h >= 150:
                        found_windows.append((hwnd, title, rect, w * h))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    found_windows.sort(key=lambda x: x[3], reverse=True)
    print('Found windows:', [(x[0], x[1], x[3]) for x in found_windows])

    if found_windows:
        target_hwnd, title, rect, area = found_windows[0]
        print(f'Activating target_hwnd={target_hwnd}, title={title}')
        
        # Restore if minimized
        if user32.IsIconic(target_hwnd):
            user32.ShowWindow(target_hwnd, 9)
        else:
            user32.ShowWindow(target_hwnd, 5)

        # Force foreground
        fg_w = user32.GetForegroundWindow()
        fg_pid = wintypes.DWORD()
        fg_tid = user32.GetWindowThreadProcessId(fg_w, byref(fg_pid))
        curr_tid = kernel32.GetCurrentThreadId()
        if fg_tid != curr_tid and fg_tid != 0:
            user32.AttachThreadInput(curr_tid, fg_tid, True)
            user32.SetForegroundWindow(target_hwnd)
            user32.BringWindowToTop(target_hwnd)
            user32.AttachThreadInput(curr_tid, fg_tid, False)
        else:
            user32.SetForegroundWindow(target_hwnd)
            user32.BringWindowToTop(target_hwnd)
        
        time.sleep(0.3)
        print('Foreground window:', user32.GetForegroundWindow())

        # Find RichEdit or Edit child control, or use client area
        child_edits = []
        def child_cb(ch, _):
            cbuf = create_unicode_buffer(256)
            user32.GetClassNameW(ch, cbuf, 256)
            if cbuf.value in ['RichEditD2DPT', 'Edit']:
                crect = RECT()
                user32.GetWindowRect(ch, byref(crect))
                child_edits.append((ch, cbuf.value, crect))
            return True
        WNDENUMPROC_CH = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(target_hwnd, WNDENUMPROC_CH(child_cb), 0)
        print('Found child edits:', child_edits)

        if child_edits:
            ch, cname, crect = child_edits[0]
            cx = crect.left + (crect.right - crect.left) // 2
            cy = crect.top + (crect.bottom - crect.top) // 2
        else:
            # Fallback: click middle of the document area (y = top + 50% of height)
            cx = rect.left + (rect.right - rect.left) // 2
            cy = rect.top + int((rect.bottom - rect.top) * 0.5)

        print(f'Clicking client document area at ({cx}, {cy})')
        input_controller.click_point(cx, cy)
        time.sleep(0.3)

        # Send text
        test_text = "Hello I am Negasaurus."
        print(f'Typing: {test_text}')
        input_controller.type_unicode_text(test_text)
        time.sleep(0.5)

        # Take screenshot and check OCR
        snap_path = "scratch/test_notepad_typed_success.png"
        capture_desktop(snap_path)
        ocr_res = asyncio.run(ocr_service.extract_text(snap_path, {"foreground_window": "Notepad"}))
        transcript = ocr_res.get("full_transcript", "")
        print(f'OCR transcript:\n{transcript}')
        found_in_ocr = test_text.lower() in transcript.lower() or "negasaurus" in transcript.lower()
        print('VERIFICATION RESULT: found_in_ocr =', found_in_ocr)

finally:
    proc.terminate()
    proc.wait()


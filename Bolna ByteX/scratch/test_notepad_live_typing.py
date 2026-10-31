import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
import subprocess, time, ctypes
from ctypes import wintypes, create_unicode_buffer, byref
from security.permissions import RECT
from services.input_controller import input_controller

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

proc = subprocess.Popen(['notepad.exe'])
time.sleep(1.2)
try:
    # 1. Enumerate windows without switching thread desktop
    notepad_hwnds = []
    def cb(h, _):
        if user32.IsWindowVisible(h):
            buf = create_unicode_buffer(512)
            user32.GetWindowTextW(h, buf, 512)
            t = buf.value
            if 'notepad' in t.lower() and 'popuphost' not in t.lower():
                notepad_hwnds.append(h)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    print('Found Notepad HWNDs:', notepad_hwnds)
    
    if notepad_hwnds:
        notepad_hwnd = notepad_hwnds[0]
        # Restore and foreground
        user32.ShowWindow(notepad_hwnd, 9)
        time.sleep(0.1)
        # Use AttachThreadInput to ensure SetForegroundWindow works
        fg_w = user32.GetForegroundWindow()
        fg_pid = wintypes.DWORD()
        fg_tid = user32.GetWindowThreadProcessId(fg_w, byref(fg_pid))
        curr_tid = kernel32.GetCurrentThreadId()
        if fg_tid != curr_tid:
            user32.AttachThreadInput(curr_tid, fg_tid, True)
            user32.SetForegroundWindow(notepad_hwnd)
            user32.BringWindowToTop(notepad_hwnd)
            user32.AttachThreadInput(curr_tid, fg_tid, False)
        else:
            user32.SetForegroundWindow(notepad_hwnd)
            user32.BringWindowToTop(notepad_hwnd)

        time.sleep(0.2)
        print('Foreground Window is now:', user32.GetForegroundWindow())

        # Find document/edit client area
        rect = RECT()
        user32.GetWindowRect(notepad_hwnd, byref(rect))
        print(f'Window rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom})')

        # Find RichEdit or Edit child control
        child_edits = []
        def c_cb(ch, _):
            cbuf = create_unicode_buffer(256)
            user32.GetClassNameW(ch, cbuf, 256)
            if cbuf.value in ['RichEditD2DPT', 'Edit']:
                child_edits.append(ch)
            return True
        WNDENUMPROC_CH = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(notepad_hwnd, WNDENUMPROC_CH(c_cb), 0)
        print('Child edit controls:', child_edits)

        if child_edits:
            crect = RECT()
            user32.GetWindowRect(child_edits[0], byref(crect))
            cx = crect.left + (crect.right - crect.left) // 2
            cy = crect.top + (crect.bottom - crect.top) // 2
        else:
            # Click center of window
            cx = rect.left + (rect.right - rect.left) // 2
            cy = rect.top + int((rect.bottom - rect.top) * 0.5)

        print(f'Clicking at ({cx}, {cy})')
        input_controller.click_point(cx, cy)
        time.sleep(0.3)

        # Type text
        text = "Hello I am Negasaurus."
        print(f'Typing text: {text}')
        input_controller.type_unicode_text(text)
        time.sleep(0.5)

        # Test verification via OCR
        from services.screenshot_helper import capture_desktop
        from services.ocr_service import ocr_service
        import asyncio
        snap = "scratch/test_notepad_real_typed.png"
        capture_desktop(snap)
        res = asyncio.run(ocr_service.extract_text(snap, {"foreground_window": "Notepad"}))
        print(f"OCR Transcript: {res.get('full_transcript')}")
        print("Text present in OCR?", text.lower() in res.get("full_transcript", "").lower())
finally:
    proc.terminate()
    proc.wait()

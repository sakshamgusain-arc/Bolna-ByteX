import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
import subprocess, time, ctypes
from ctypes import wintypes, create_unicode_buffer, c_ulong, byref
from security.permissions import RECT

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

proc = subprocess.Popen(['notepad.exe'])

try:
    found_windows = []
    for _ in range(15):
        time.sleep(0.2)
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
        if found_windows:
            break

    found_windows.sort(key=lambda x: x[3], reverse=True)
    print('Found windows:', [(x[0], x[1], x[3]) for x in found_windows])

    if found_windows:
        target_hwnd = found_windows[0][0]
        
        fg_hwnd = user32.GetForegroundWindow()
        target_pid = c_ulong()
        target_tid = user32.GetWindowThreadProcessId(target_hwnd, byref(target_pid))
        fg_pid = c_ulong()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, byref(fg_pid))
        cur_tid = kernel32.GetCurrentThreadId()

        # Attach thread input
        if target_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, target_tid, True)
        if fg_tid != 0 and fg_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, True)

        # Release lock with ALT tap
        user32.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.02)

        user32.ShowWindow(target_hwnd, 9)
        user32.BringWindowToTop(target_hwnd)
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.25)

        if target_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, target_tid, False)
        if fg_tid != 0 and fg_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, False)

        fg_after = user32.GetForegroundWindow()
        print(f'Target HWND: {target_hwnd}, Foreground after: {fg_after}, Success: {fg_after == target_hwnd}')

        # Click inside document
        rect = RECT()
        user32.GetWindowRect(target_hwnd, byref(rect))
        cx = rect.left + (rect.right - rect.left) // 2
        cy = rect.top + int((rect.bottom - rect.top) * 0.5)
        print(f'Clicking document at ({cx}, {cy})')
        from services.input_controller import input_controller
        input_controller.click_point(cx, cy)
        time.sleep(0.25)

        # Type text
        text = "Hello I am Negasaurus."
        print(f'Typing: {text}')
        input_controller.type_unicode_text(text)
        time.sleep(0.5)

        # Check RichEdit child
        children = []
        def c_cb(ch, _):
            buf = create_unicode_buffer(256)
            user32.GetClassNameW(ch, buf, 256)
            if buf.value in ['RichEditD2DPT', 'Edit']:
                children.append((ch, buf.value))
            return True
        WNDENUMPROC_CH = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(target_hwnd, WNDENUMPROC_CH(c_cb), 0)
        print('Child controls found:', children)

        if children:
            ch, cname = children[0]
            l = user32.SendMessageW(ch, 0x000E, 0, 0)
            print(f'WM_GETTEXTLENGTH on {cname}: {l}')
            if l > 0:
                tbuf = create_unicode_buffer(l + 1)
                user32.SendMessageW(ch, 0x000D, l + 1, tbuf)
                print(f'WM_GETTEXT: {tbuf.value!r}')

finally:
    proc.terminate()
    proc.wait()

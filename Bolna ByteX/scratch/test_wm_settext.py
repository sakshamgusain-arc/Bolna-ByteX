import subprocess
import time
import ctypes
from ctypes import wintypes, create_unicode_buffer, byref, c_ulong, Structure, sizeof, c_char_p, c_void_p

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

proc = subprocess.Popen(["notepad.exe"])

try:
    for _ in range(15):
        time.sleep(0.2)
        hwnds = []
        def enum_cb(h, _):
            if user32.IsWindowVisible(h):
                buf = create_unicode_buffer(512)
                user32.GetWindowTextW(h, buf, 512)
                if "notepad" in buf.value.lower() and "popuphost" not in buf.value.lower():
                    hwnds.append(h)
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if hwnds:
            break

    target_hwnd = hwnds[0]
    print(f"Target Notepad HWND: {target_hwnd}")

    # Find RichEdit child
    children = []
    def c_cb(ch, _):
        buf = create_unicode_buffer(256)
        user32.GetClassNameW(ch, buf, 256)
        if buf.value in ['RichEditD2DPT', 'Edit']:
            children.append((ch, buf.value))
        return True
    WNDENUMPROC_CH = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(target_hwnd, WNDENUMPROC_CH(c_cb), 0)
    print(f"Children: {children}")

    if children:
        ch, cname = children[0]
        test_str = "Negasaurus Test String 123"
        print(f"Sending WM_SETTEXT to {cname}...")
        res = user32.SendMessageW(ch, 0x000C, 0, test_str) # WM_SETTEXT
        print(f"WM_SETTEXT result: {res}")

        # Now test reading back via WM_GETTEXTLENGTH and WM_GETTEXT
        l = user32.SendMessageW(ch, 0x000E, 0, 0)
        print(f"WM_GETTEXTLENGTH on {cname}: {l}")
        if l > 0:
            buf = create_unicode_buffer(l + 1)
            user32.SendMessageW(ch, 0x000D, l + 1, buf)
            print(f"WM_GETTEXT read back: '{buf.value}'")

finally:
    proc.terminate()
    proc.wait()


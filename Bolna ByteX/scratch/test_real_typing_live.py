import subprocess
import time
import ctypes
from ctypes import wintypes, byref, sizeof

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_size_t)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_size_t)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD)
    ]

class _INPUTunion(ctypes.Union):
    _fields_ = [
        ('mi', MOUSEINPUT),
        ('ki', KEYBDINPUT),
        ('hi', HARDWAREINPUT)
    ]

class REAL_INPUT(ctypes.Structure):
    _fields_ = [
        ('type', wintypes.DWORD),
        ('union', _INPUTunion)
    ]

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

print("Launching Notepad...")
proc = subprocess.Popen(["notepad.exe"])
time.sleep(2.0)

try:
    notepad_hwnds = []
    def enum_cb(h, _):
        if user32.IsWindowVisible(h):
            t = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, t, 256)
            if "notepad" in t.value.lower() and "popuphost" not in t.value.lower():
                notepad_hwnds.append(h)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    print(f"Notepad HWNDs: {notepad_hwnds}")
    notepad_hwnd = notepad_hwnds[0]

    # Attach desktop context
    h_in = user32.OpenInputDesktop(0, False, 0x01FF)
    old_d = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    user32.SetThreadDesktop(h_in)

    # Bring to foreground
    user32.ShowWindow(notepad_hwnd, 9)
    user32.BringWindowToTop(notepad_hwnd)
    user32.SetForegroundWindow(notepad_hwnd)
    time.sleep(0.3)

    # Click document canvas
    rect = wintypes.RECT()
    user32.GetWindowRect(notepad_hwnd, byref(rect))
    cx = rect.left + (rect.right - rect.left) // 2
    cy = rect.top + int((rect.bottom - rect.top) * 0.55)
    print(f"Clicking at ({cx}, {cy})...")
    user32.SetCursorPos(cx, cy)
    time.sleep(0.05)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.2)

    # Type text using 40-byte REAL_INPUT
    test_text = "Hello I am Negasaurus."
    print(f"Typing '{test_text}' via SendInput...")
    total_inserted = 0
    for ch in test_text:
        code = ord(ch)
        inp_down = REAL_INPUT()
        inp_down.type = 1
        inp_down.union.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=4, time=0, dwExtraInfo=0)
        inp_up = REAL_INPUT()
        inp_up.type = 1
        inp_up.union.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=4 | 2, time=0, dwExtraInfo=0)

        r1 = user32.SendInput(1, byref(inp_down), sizeof(REAL_INPUT))
        r2 = user32.SendInput(1, byref(inp_up), sizeof(REAL_INPUT))
        total_inserted += (r1 + r2)
        time.sleep(0.015)

    print(f"SendInput Total Inserted: {total_inserted} of {len(test_text)*2}")
    user32.SetThreadDesktop(old_d)
    user32.CloseDesktop(h_in)
    time.sleep(0.5)

    # Read back document content using UI Automation
    ps_cmd = f"""
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{notepad_hwnd})
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
    $doc = $el.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($doc) {{
        $tp = $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
        Write-Output "UIA Document Text: '$($tp.DocumentRange.GetText(-1))'"
    }} else {{
        Write-Output "Document element not found"
    }}
    """
    res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd], capture_output=True, text=True)
    print(f"Read-back result:\n{res.stdout.strip()}")

finally:
    proc.terminate()
    proc.wait()

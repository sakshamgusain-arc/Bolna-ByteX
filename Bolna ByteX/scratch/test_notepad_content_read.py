import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

import subprocess
import time
import ctypes
from ctypes import wintypes, byref, create_unicode_buffer
from security.permissions import RECT, SecurityPermissions
from services.input_controller import input_controller

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

proc = subprocess.Popen(["notepad.exe"])
time.sleep(1.2)

try:
    # Use SecurityPermissions.verify_application_window
    ver = SecurityPermissions.verify_application_window("notepad", target_pid=proc.pid)
    print(f"verify_application_window: {ver}")
    nh = ver["hwnd"]
    
    fg = user32.GetForegroundWindow()
    print(f"Current Foreground Window: {fg}, Notepad HWND: {nh}")

    # Check rect
    rect = RECT()
    user32.GetWindowRect(nh, byref(rect))
    print(f"Notepad rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom})")

    # Click inside Notepad document area
    cx = rect.left + (rect.right - rect.left) // 2
    cy = rect.top + (rect.bottom - rect.top) // 2
    print(f"Clicking client area: ({cx}, {cy})")
    input_controller.click_point(cx, cy)
    time.sleep(0.3)

    fg2 = user32.GetForegroundWindow()
    print(f"Foreground after click: {fg2} (matches nh: {fg2 == nh})")

    # Now type
    print("Typing text...")
    input_controller.type_unicode_text("Hello I am Negasaurus.")
    time.sleep(0.5)

    # Capture screenshot and check
    from services.screenshot_helper import capture_desktop
    snap = "scratch/test_snap_client.png"
    capture_desktop(snap)
    print("Screenshot captured to", snap)

finally:
    proc.terminate()
    proc.wait()

import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

import subprocess
import time
import ctypes
from ctypes import wintypes, create_unicode_buffer, byref, sizeof, c_ulong
import psutil

from security.permissions import RECT, SecurityPermissions
from services.input_controller import InputController, is_windows, INPUT, KEYBDINPUT
from services.screenshot_helper import capture_desktop
from services.ocr_service import ocr_service
from services.visual_verifier import VisualVerifier

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

print("=====================================================================")
print("BYTE-X CORE: REAL WINDOWS RUNTIME NOTEPAD DIAGNOSTIC")
print("=====================================================================")

# Step 0: Ensure a clean Notepad process is launched as ByteX does
for p in psutil.process_iter(['pid', 'name']):
    if 'notepad' in p.info['name'].lower():
        try:
            p.kill()
        except Exception:
            pass
time.sleep(1.0)

print("\n[STEP 1 & 2] Launching Notepad and running verify_application_window with polling...")
proc = subprocess.Popen(["notepad.exe"])

win_info = None
notepad_hwnd = None

for attempt in range(10):
    time.sleep(0.5)
    win_info = SecurityPermissions.verify_application_window("notepad")
    notepad_hwnd = win_info.get("hwnd")
    print(f"  Attempt {attempt+1} (t={(attempt+1)*0.5}s): verified={win_info.get('verified')}, hwnd={notepad_hwnd}, title='{win_info.get('window_title')}'")
    if notepad_hwnd:
        break

if not notepad_hwnd:
    # Let's inspect all top level windows to see what is on the desktop right now
    all_wins = []
    def enum_debug(h, _):
        if user32.IsWindowVisible(h):
            t = create_unicode_buffer(256)
            user32.GetWindowTextW(h, t, 256)
            c = create_unicode_buffer(256)
            user32.GetClassNameW(h, c, 256)
            p = c_ulong()
            user32.GetWindowThreadProcessId(h, byref(p))
            if t.value or 'note' in c.value.lower():
                all_wins.append((h, p.value, c.value, t.value))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_debug), 0)
    print("All visible windows with titles:")
    for w in all_wins:
        print(f"  HWND={w[0]}, PID={w[1]}, Class='{w[2]}', Title='{w[3]}'")
    print("FATAL: Notepad HWND not found after polling!")
    sys.exit(1)

# Item 1 & 2: Log HWND, PID, process name, title, class, visibility, dimensions
pid = c_ulong()
tid = user32.GetWindowThreadProcessId(notepad_hwnd, byref(pid))
pname = ""
try:
    pname = psutil.Process(pid.value).name()
except Exception:
    pass
tbuf = create_unicode_buffer(512)
user32.GetWindowTextW(notepad_hwnd, tbuf, 512)
cbuf = create_unicode_buffer(256)
user32.GetClassNameW(notepad_hwnd, cbuf, 256)
w_visible = bool(user32.IsWindowVisible(notepad_hwnd))
rect = RECT()
user32.GetWindowRect(notepad_hwnd, byref(rect))
w_dims = (rect.right - rect.left, rect.bottom - rect.top)

print("\n--- NOTEPAD WINDOW DETAILS ---")
print(f"1. Target HWND:       {notepad_hwnd} (Hex: {hex(notepad_hwnd)})")
print(f"2. PID / TID:         {pid.value} / {tid}")
print(f"3. Process Name:      {pname}")
print(f"4. Window Title:      '{tbuf.value}'")
print(f"5. Class Name:        '{cbuf.value}'")
print(f"6. Is Visible:        {w_visible}")
print(f"7. Dimensions (w x h):{w_dims} | Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom})")
print(f"8. Is Iconic / Min:   {bool(user32.IsIconic(notepad_hwnd))}")

# Item 4: Child Windows and Editor Control
print("\n--- CHILD WINDOWS ENUMERATION ---")
child_windows = []
def child_cb(ch, _):
    c_buf = create_unicode_buffer(256)
    user32.GetClassNameW(ch, c_buf, 256)
    t_buf = create_unicode_buffer(256)
    user32.GetWindowTextW(ch, t_buf, 256)
    c_rect = RECT()
    user32.GetWindowRect(ch, byref(c_rect))
    child_windows.append({
        "hwnd": ch,
        "class": c_buf.value,
        "title": t_buf.value,
        "rect": (c_rect.left, c_rect.top, c_rect.right, c_rect.bottom),
        "dims": (c_rect.right - c_rect.left, c_rect.bottom - c_rect.top),
        "visible": bool(user32.IsWindowVisible(ch))
    })
    return True

WNDENUMPROC_CH = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumChildWindows(notepad_hwnd, WNDENUMPROC_CH(child_cb), 0)

for idx, ch in enumerate(child_windows):
    print(f"  [{idx}] HWND={ch['hwnd']} | Class='{ch['class']}' | Title='{ch['title']}' | Dims={ch['dims']} | Visible={ch['visible']}")

editor_candidates = [ch for ch in child_windows if ch['class'] in ["RichEditD2DPT", "NotepadTextBox", "Edit"]]
print(f"\nEditor Candidates Found: {len(editor_candidates)}")
editor_hwnd = editor_candidates[0]['hwnd'] if editor_candidates else None
if editor_candidates:
    print(f"  Selected Editor HWND: {editor_hwnd} (Class: '{editor_candidates[0]['class']}')")
else:
    print("  WARNING: No standard Edit/RichEdit child window found!")

# Item 3 & 5: Foreground & Focus Inspection Before Clicking/Typing
print("\n--- FOREGROUND & FOCUS STATE BEFORE FOCUSING ---")
fg_before = user32.GetForegroundWindow()
fg_tbuf = create_unicode_buffer(512)
user32.GetWindowTextW(fg_before, fg_tbuf, 512)
print(f"Foreground HWND: {fg_before} ('{fg_tbuf.value}') | Matches Notepad: {fg_before == notepad_hwnd}")

cur_tid = kernel32.GetCurrentThreadId()
user32.AttachThreadInput(cur_tid, tid, True)
focus_before = user32.GetFocus()
f_cls_buf = create_unicode_buffer(256)
user32.GetClassNameW(focus_before, f_cls_buf, 256)
user32.AttachThreadInput(cur_tid, tid, False)
print(f"Focused HWND in Notepad thread: {focus_before} (Class: '{f_cls_buf.value}')")

# Capture Screenshot 1: Before Typing
os.makedirs("scratch", exist_ok=True)
snap_pre = "scratch/diag_pre_typing.png"
capture_desktop(snap_pre)
print(f"Captured Pre-Typing Screenshot -> {snap_pre}")

# Read Document Content Before Typing
def read_doc_win32(h):
    if not h: return ""
    txts = []
    targets = [editor_hwnd, h] if editor_hwnd else [h]
    for target in targets:
        if not target: continue
        l = user32.SendMessageW(target, 0x000E, 0, 0)
        if l > 0:
            b = create_unicode_buffer(l + 1)
            user32.SendMessageW(target, 0x000D, l + 1, b)
            if b.value:
                txts.append(b.value)
    return "\n".join(txts)

doc_before_win32 = read_doc_win32(notepad_hwnd)
print(f"Win32 Document Content Before: '{doc_before_win32}' (Length: {len(doc_before_win32)})")

# Item 6: Desktop Context Attachment Test
print("\n--- DESKTOP CONTEXT ATTACHMENT ---")
h_in, old_d = InputController._attach_desktop_context()
curr_d = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
print(f"OpenInputDesktop handle: {h_in}")
print(f"Original ThreadDesktop:   {old_d}")
print(f"Active ThreadDesktop:     {curr_d}")
print(f"Desktop Context Attached: {h_in is not None and curr_d == h_in}")

# Attempt to bring to foreground and focus
print("\n--- FOCUSING & CLICKING DOCUMENT CANVAS ---")
user32.ShowWindow(notepad_hwnd, 9)
user32.BringWindowToTop(notepad_hwnd)
user32.SetForegroundWindow(notepad_hwnd)
time.sleep(0.3)

if editor_candidates:
    er = editor_candidates[0]['rect']
    cx = er[0] + 50
    cy = er[1] + 50
else:
    cx = rect.left + (rect.right - rect.left) // 2
    cy = rect.top + int((rect.bottom - rect.top) * 0.5)

print(f"Clicking at ({cx}, {cy}) to set focus...")
InputController.click_point(cx, cy)
time.sleep(0.3)

# Inspect Foreground and Focus immediately before typing
fg_typing = user32.GetForegroundWindow()
fg_tbuf2 = create_unicode_buffer(512)
user32.GetWindowTextW(fg_typing, fg_tbuf2, 512)
print(f"Foreground HWND Immediately Before Typing: {fg_typing} ('{fg_tbuf2.value}') | Matches Notepad: {fg_typing == notepad_hwnd}")

user32.AttachThreadInput(cur_tid, tid, True)
focus_typing = user32.GetFocus()
f_cls_buf2 = create_unicode_buffer(256)
user32.GetClassNameW(focus_typing, f_cls_buf2, 256)
user32.AttachThreadInput(cur_tid, tid, False)
print(f"Focused HWND in Notepad thread Immediately Before Typing: {focus_typing} (Class: '{f_cls_buf2.value}') | Matches Editor: {focus_typing == editor_hwnd}")

# Item 7: SendInput Execution and Return Value
text_to_type = "Hello I am Negasaurus."
print(f"\n--- DISPATCHING SENDINPUT: '{text_to_type}' ---")
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002

total_chars = len(text_to_type)
inserted_events = 0
failed_events = 0

for ch in text_to_type:
    code = ord(ch)
    inp_down = INPUT(type=INPUT_KEYBOARD)
    inp_down.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
    inp_up = INPUT(type=INPUT_KEYBOARD)
    inp_up.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

    r1 = user32.SendInput(1, byref(inp_down), sizeof(INPUT))
    r2 = user32.SendInput(1, byref(inp_up), sizeof(INPUT))
    inserted_events += (r1 + r2)
    if r1 == 0 or r2 == 0:
        failed_events += 1
    time.sleep(0.015)

print(f"SendInput Dispatched: Expected {total_chars * 2} events. Inserted: {inserted_events}, Failed calls: {failed_events}")

# Clean up desktop context
InputController._detach_desktop_context(h_in, old_d)
time.sleep(0.5)

# Item 8: Read Document Content Immediately After Typing
print("\n--- DOCUMENT CONTENT IMMEDIATELY AFTER TYPING ---")
doc_after_win32 = read_doc_win32(notepad_hwnd)
print(f"Win32 WM_GETTEXT After Typing: '{doc_after_win32}' (Length: {len(doc_after_win32)})")

# Capture Screenshot 2: Immediately After Typing
snap_post = "scratch/diag_post_typing.png"
capture_desktop(snap_post)
print(f"Captured Post-Typing Screenshot -> {snap_post}")

# Compute image diff
diff_metric = VisualVerifier.compute_image_diff_metric(snap_pre, snap_post)
print(f"Screenshot Pixel Diff Metric: {diff_metric:.6f} (Threshold: > 0.0001)")

# Item 9: OCR and Verification Analysis
print("\n--- OCR READING & VERIFICATION EVIDENCE ---")
import asyncio
loop = asyncio.new_event_loop()
ocr_res = loop.run_until_complete(ocr_service.extract_text(snap_post, {"foreground_window": "Notepad"}, target_query=text_to_type))
print(f"OCR Full Transcript: '{ocr_res.get('full_transcript')}'")
print(f"Text in OCR Transcript? {text_to_type.lower() in ocr_res.get('full_transcript', '').lower()}")

# Test UI Automation reading via PowerShell
print("\n--- WINDOWS UI AUTOMATION INSPECTION ---")
ps_script = f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$hwnd = [IntPtr]{notepad_hwnd}
$el = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($el) {{
    Write-Output "UIA Root: $($el.Current.Name)"
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
    $doc = $el.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if (-not $doc) {{
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
        $doc = $el.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    }}
    if ($doc) {{
        Write-Output "Found Document/Edit Control: $($doc.Current.Name) Class=$($doc.Current.ClassName)"
        try {{
            $tp = $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $txt = $tp.DocumentRange.GetText(-1)
            Write-Output "UIA TextPattern: '$txt'"
        }} catch {{
            Write-Output "UIA TextPattern Failed: $_"
        }}
        try {{
            $vp = $doc.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            Write-Output "UIA ValuePattern: '$($vp.Current.Value)'"
        }} catch {{
            Write-Output "UIA ValuePattern Failed: $_"
        }}
    }} else {{
        Write-Output "UIA Document/Edit Control Not Found directly"
    }}
}}
"""
ps_res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script], capture_output=True, text=True)
print(f"UIA Inspection Output:\n{ps_res.stdout.strip()}")

print("\n=====================================================================")
print("DIAGNOSTIC COMPLETED")
print("=====================================================================")

import subprocess, time, ctypes
from ctypes import wintypes, create_unicode_buffer

user32 = ctypes.windll.user32
proc = subprocess.Popen(["notepad.exe"])
time.sleep(2.0)
try:
    hwnds = []
    def enum_cb(h, _):
        if user32.IsWindowVisible(h):
            t = create_unicode_buffer(256)
            user32.GetWindowTextW(h, t, 256)
            if "notepad" in t.value.lower() and "popuphost" not in t.value.lower():
                hwnds.append(h)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    nh = hwnds[0]
    print("Notepad HWND:", nh)

    # Let's use UI Automation ValuePattern or send keys to type into it, or WM_SETTEXT
    # Wait, earlier we saw WM_SETTEXT on RichEditD2DPT worked! But does ValuePattern.SetValue work via UIA?
    ps_script = f"""
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{nh})
    
    $condDoc = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
    $doc = $el.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condDoc)
    if ($doc) {{
        # Try ValuePattern.SetValue
        try {{
            $vp = $doc.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $vp.SetValue("Hello I am Negasaurus.")
            Write-Output "SetValue succeeded"
        }} catch {{
            Write-Output "SetValue failed: $_"
        }}

        # Read with TextPattern
        try {{
            $tp = $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $txt = $tp.DocumentRange.GetText(-1)
            Write-Output "READ_BACK_TEXT:$txt"
        }} catch {{
            Write-Output "TextPattern failed: $_"
        }}
    }}
    """
    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script], capture_output=True, text=True)
    print("STDOUT:\n", res.stdout)
    print("STDERR:\n", res.stderr)
finally:
    proc.terminate()

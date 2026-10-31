Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;

public class Win32Helper {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    public static IntPtr FindRichEditHwnd() {
        IntPtr result = IntPtr.Zero;
        EnumWindows((hWnd, lParam) => {
            if (IsWindowVisible(hWnd)) {
                StringBuilder sb = new StringBuilder(256);
                GetWindowText(hWnd, sb, 256);
                string t = sb.ToString();
                if (t.ToLower().Contains("notepad") && !t.ToLower().Contains("popuphost")) {
                    EnumChildWindows(hWnd, (ch, chParam) => {
                        StringBuilder cls = new StringBuilder(256);
                        GetClassName(ch, cls, 256);
                        if (cls.ToString() == "RichEditD2DPT" || cls.ToString() == "Edit") {
                            result = ch;
                            return false;
                        }
                        return true;
                    }, IntPtr.Zero);
                    if (result != IntPtr.Zero) return false;
                }
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }
}
"@

$proc = Start-Process notepad.exe -PassThru
Start-Sleep -Seconds 1.5

try {
    $richHwnd = [Win32Helper]::FindRichEditHwnd()
    Write-Output "RichEdit HWND: $richHwnd"
    if ($richHwnd -ne [IntPtr]::Zero) {
        $el = [System.Windows.Automation.AutomationElement]::FromHandle($richHwnd)
        Write-Output "Element Name='$($el.Current.Name)', Type='$($el.Current.ControlType.ProgrammaticName)', Class='$($el.Current.ClassName)'"
        $patterns = $el.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }
        Write-Output "Patterns: $($patterns -join ", ")"
        
        # Check TextPattern
        try {
            $tp = $el.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $text = $tp.DocumentRange.GetText(-1)
            Write-Output "TextPattern Document Text: '$text'"
        } catch {
            Write-Output "TextPattern error: $_"
        }
        
        # Check ValuePattern
        try {
            $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            Write-Output "ValuePattern Text: '$($vp.Current.Value)'"
        } catch {
            Write-Output "ValuePattern error: $_"
        }
    }
} finally {
    Stop-Process -Name notepad -Force -ErrorAction SilentlyContinue
}

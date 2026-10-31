import os
import re
import ctypes
from ctypes import windll, byref, c_ulong, create_unicode_buffer
import psutil
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from ctypes import wintypes
user32 = windll.user32
kernel32 = windll.kernel32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

ALLOWED_APPLICATIONS = {
    "chrome": ["chrome", "google chrome"],
    "edge": ["edge", "msedge", "microsoft edge"],
    "notepad": ["notepad"],
    "calc": ["calc", "calculator"],
    "code": ["code", "vscode", "visual studio code"],
    "mspaint": ["mspaint", "paint"],
    "cmd": ["cmd", "command prompt"],
    "powershell": ["powershell"],
    "explorer": ["explorer", "file explorer"],
    "discord": ["discord"],
    "spotify": ["spotify"],
    "whatsapp": ["whatsapp", "whatsapp desktop"],
}

BLOCKED_PATH_PATTERNS = [
    r"c:\\windows",
    r"c:\\program files",
    r"c:\\program files \(x86\)",
    r"c:\\programdata",
    r"system32",
    r"syswow64",
    r"system volume information",
    r"\.env",
    r"credentials",
    r"passwords?",
    r"id_rsa",
    r"\.pem$",
    r"\.key$",
    r"shadow",
]

# Hidden background system window titles to ignore
IGNORE_WINDOW_TITLES = {
    "tooltip",
    "default ime",
    "cicerouiwndframe",
    "tf_floatinglangbar_wndtitle",
    "gdi+ window (notepad.exe)",
    "popuphost",
}

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG)
    ]

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

class SecurityPermissions:
    """Security permissions & allowlist enforcement engine."""

    @staticmethod
    def get_allowed_app_key(app_name: str) -> Optional[str]:
        """Resolves raw application input to an allowlisted app key, validated catalog target, or valid .lnk shortcut."""
        norm = app_name.strip().lower()
        for key, aliases in ALLOWED_APPLICATIONS.items():
            if norm == key or norm in aliases:
                return key
        
        # Check against Universal Application Resolver (Start Menu, Desktop, Registry, Builtins)
        try:
            from skills.resolver import universal_app_resolver, ResolutionStatus
            status, rec, _ = universal_app_resolver.resolve(app_name)
            if status == ResolutionStatus.FOUND and rec:
                return rec.normalized_name
        except Exception:
            pass

        # Check if input corresponds to an existing .lnk shortcut on the system
        from skills.apps import find_matching_shortcut
        try:
            lnk = find_matching_shortcut(app_name)
            if lnk and lnk.exists():
                return str(lnk)
        except Exception:
            pass

        return None

    @staticmethod
    def get_allowed_app_executable(app_name: str) -> Optional[str]:
        """Alias for get_allowed_app_key."""
        return SecurityPermissions.get_allowed_app_key(app_name)

    @staticmethod
    def resolve_executable_path(app_key: str) -> Tuple[Optional[str], List[str], List[str]]:
        """
        Resolves trusted executable path, process keywords, and window title keywords.
        Returns: (executable_cmd, process_keywords, title_keywords)
        """
        key = app_key.lower().strip()
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", r"C:\Users\ryzzn\AppData\Local")

        if key in ["chrome", "google chrome"]:
            candidates = [
                os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
                os.path.join(pfx86, r"Google\Chrome\Application\chrome.exe"),
                os.path.join(local_app, r"Google\Chrome\Application\chrome.exe"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    return f'"{c}"', ["chrome"], ["chrome"]
            return "start chrome", ["chrome"], ["chrome"]

        if key in ["edge", "msedge", "microsoft edge"]:
            candidates = [
                os.path.join(pfx86, r"Microsoft\Edge\Application\msedge.exe"),
                os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"),
                os.path.join(local_app, r"Microsoft\Edge\Application\msedge.exe"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    return f'"{c}"', ["msedge", "edge", "microsoft edge"], ["edge", "microsoft edge", "msedge"]
            return "start msedge", ["msedge", "edge", "microsoft edge"], ["edge", "microsoft edge", "msedge"]

        if key == "notepad":
            return "notepad.exe", ["notepad"], ["notepad"]

        if key in ["calc", "calculator"]:
            return "calc.exe", ["calc", "calculator"], ["calculator", "calc"]

        if key in ["code", "vscode"]:
            return "code", ["code"], ["visual studio code", "code"]

        if key in ["mspaint", "paint"]:
            return "mspaint.exe", ["mspaint"], ["paint"]

        if key in ["cmd", "command prompt"]:
            return "cmd.exe", ["cmd"], ["command prompt", "cmd"]

        if key == "powershell":
            return "powershell.exe", ["powershell"], ["powershell"]

        if key in ["explorer", "file explorer"]:
            return "explorer.exe", ["explorer"], ["explorer", "file explorer"]

        if key == "discord":
            return "Discord.exe", ["discord"], ["discord"]

        if key == "spotify":
            return "Spotify.exe", ["spotify"], ["spotify"]

        if key in ["whatsapp", "whatsapp desktop"]:
            return "whatsapp:", ["whatsapp", "whatsapp.root"], ["whatsapp"]

        return None, [key], [key]

    @staticmethod
    def verify_application_window(app_key: str, target_pid: Optional[int] = None, target_hwnd: Optional[int] = None) -> Dict[str, Any]:
        """
        Generic Windows Window Verification Helper.
        Enumerates top-level Windows desktop windows using User32 EnumWindows API.
        Checks for REAL visible windows (filtering out hidden IME/tooltip frames),
        ensures the window is on-screen, restores minimized windows, forces foreground focus,
        and returns structured inspection data.
        """
        exe_cmd, proc_keywords, title_keywords = SecurityPermissions.resolve_executable_path(app_key)
        if not exe_cmd and target_pid is None and target_hwnd is None:
            return {
                "verified": False,
                "process_found": False,
                "window_found": False,
                "visible": False,
                "window_title": "",
                "pid": None,
                "hwnd": None
            }

        found_windows = []

        def enum_window_callback(hwnd, lParam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip()
                    title_clean = title.replace("\u200b", "").lower()

                    # Ignore internal hidden background UI titles and popups
                    if title_clean in IGNORE_WINDOW_TITLES or title_clean.startswith("gdi+") or "popuphost" in title_clean:
                        return True

                    pid = c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, byref(pid))

                    proc_name = ""
                    try:
                        p = psutil.Process(pid.value)
                        proc_name = p.name().lower()
                    except Exception:
                        pass

                    proc_matched = any(kw in proc_name for kw in proc_keywords) if proc_name else False
                    title_matched = any(kw in title_clean for kw in title_keywords)

                    if target_hwnd is not None and hwnd != target_hwnd:
                        return True

                    if target_pid is not None:
                        is_target = (pid.value == target_pid)
                        if not is_target:
                            try:
                                is_target = (psutil.Process(pid.value).ppid() == target_pid)
                            except Exception:
                                pass
                        # If target_pid was specified, check if matched; if not matched and no title/proc match, skip
                        if not is_target and not (proc_matched or title_matched):
                            return True

                    if proc_matched or title_matched or target_pid is not None or target_hwnd is not None:
                        rect = RECT()
                        user32.GetWindowRect(hwnd, byref(rect))
                        is_minimized = bool(user32.IsIconic(hwnd))
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        
                        # Filter out invisible or tool/popup windows (< 150x100) if not minimized
                        if not is_minimized and (w < 150 or h < 100):
                            return True

                        found_windows.append({
                            "hwnd": hwnd,
                            "pid": pid.value,
                            "proc_name": proc_name,
                            "title": title,
                            "rect": (rect.left, rect.top, rect.right, rect.bottom),
                            "minimized": is_minimized,
                            "area": w * h,
                            "title_matched": title_matched
                        })
            return True

        cb_func = WNDENUMPROC(enum_window_callback)
        user32.EnumWindows(cb_func, 0)
        if not found_windows:
            h_default = user32.OpenInputDesktop(0, False, 0x01FF)
            if not h_default:
                h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if h_default:
                try:
                    user32.EnumDesktopWindows(h_default, cb_func, 0)
                finally:
                    user32.CloseDesktop(h_default)

        # Sort candidate windows to prioritize actual main document/app windows:
        # 1. Exact/fuzzy title match over generic process name
        # 2. Largest window area (avoids tiny dialogs/toolbars/popups)
        found_windows.sort(key=lambda w: (1 if w.get("title_matched") else 0, w.get("area", 0)), reverse=True)

        # Check background process status
        proc_found = False
        if target_pid:
            proc_found = psutil.pid_exists(target_pid)
        else:
            for p in psutil.process_iter(['name']):
                try:
                    name = p.info['name']
                    if name and any(kw in name.lower() for kw in proc_keywords):
                        proc_found = True
                        break
                except Exception:
                    pass

        if not found_windows:
            print(f"[PC] Application: {app_key} | Process found: {proc_found} | Window found: False | Visible: False | Verification: False")
            return {
                "verified": False,
                "process_found": proc_found,
                "window_found": False,
                "visible": False,
                "window_title": "",
                "pid": target_pid,
                "hwnd": None
            }

        target_win = found_windows[0]
        hwnd = target_win["hwnd"]
        
        # 1. Restore window if minimized
        if target_win["minimized"]:
            user32.ShowWindow(hwnd, 9) # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5) # SW_SHOW

        # 2. Check window bounds and ensure on-screen
        rect = RECT()
        user32.GetWindowRect(hwnd, byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        
        # If off-screen or too small, reposition and size onto primary display
        if w < 300 or h < 200 or rect.right < 100 or rect.bottom < 100 or rect.left > 3000 or rect.top > 3000:
            user32.SetWindowPos(hwnd, 0, 100, 100, 1280, 800, 0x0040) # SWP_SHOWWINDOW

        # 3. Robust Foreground Window Activation and Z-Order Management
        try:
            h_input = user32.OpenInputDesktop(0, False, 0x01FF)
            old_d = None
            if h_input:
                old_d = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
                user32.SetThreadDesktop(h_input)

            # If activating browser, lower any fullscreen Antigravity/ByteX window to bottom of Z-order
            if any(k in app_key.lower() for k in ["edge", "msedge", "chrome", "brave", "firefox", "browser"]):
                def lower_antigravity_cb(h_other, lp):
                    if h_other != hwnd and user32.IsWindowVisible(h_other):
                        pid_other = c_ulong()
                        user32.GetWindowThreadProcessId(h_other, byref(pid_other))
                        try:
                            p_name = psutil.Process(pid_other.value).name().lower()
                            if "antigravity" in p_name:
                                # Send Antigravity behind the activated browser
                                user32.SetWindowPos(h_other, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010) # HWND_BOTTOM | SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
                        except Exception:
                            pass
                    return True
                
                try:
                    if h_input:
                        user32.EnumDesktopWindows(h_input, WNDENUMPROC(lower_antigravity_cb), 0)
                    else:
                        user32.EnumWindows(WNDENUMPROC(lower_antigravity_cb), 0)
                except Exception:
                    pass

            fg_hwnd = user32.GetForegroundWindow()
            cur_thread_id = kernel32.GetCurrentThreadId()
            fg_thread_id = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
            target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)

            if fg_thread_id and fg_thread_id != cur_thread_id:
                user32.AttachThreadInput(cur_thread_id, fg_thread_id, True)
            if target_thread_id and target_thread_id != cur_thread_id:
                user32.AttachThreadInput(cur_thread_id, target_thread_id, True)

            # Bypass Windows LockSetForegroundWindow via simulated Alt key tap
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            # Bring to Top and Set Foreground
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SwitchToThisWindow(hwnd, True)

            if fg_thread_id and fg_thread_id != cur_thread_id:
                user32.AttachThreadInput(cur_thread_id, fg_thread_id, False)
            if target_thread_id and target_thread_id != cur_thread_id:
                user32.AttachThreadInput(cur_thread_id, target_thread_id, False)

            if h_input and old_d:
                user32.SetThreadDesktop(old_d)
                user32.CloseDesktop(h_input)
        except Exception as e:
            print(f"[Permissions] Window foreground activation: {e}")

        # Check final foreground state
        final_fg_hwnd = user32.GetForegroundWindow()
        fg_pid = c_ulong()
        if final_fg_hwnd:
            user32.GetWindowThreadProcessId(final_fg_hwnd, byref(fg_pid))

        is_fg = bool(final_fg_hwnd == hwnd or fg_pid.value == target_win["pid"])

        clean_title = (target_win['title'] or "").encode('ascii', 'replace').decode('ascii')
        print(f"[PC] Application: {app_key} | Process found: True | Window found: True | Visible: True | Title: '{clean_title}' | PID: {target_win['pid']} | HWND: {hwnd} | Foreground: {is_fg}")

        return {
            "verified": True,
            "process_found": True,
            "window_found": True,
            "visible": True,
            "minimized": False,
            "is_foreground": is_fg,
            "hwnd": hwnd,
            "pid": target_win["pid"],
            "rect": target_win.get("rect") or (rect.left, rect.top, rect.right, rect.bottom),
            "window_title": target_win["title"]
        }

    @staticmethod
    def validate_url(url: str) -> Tuple[bool, str]:
        """Validates URL protocols, allowing only http/https."""
        url_clean = url.strip()
        if not url_clean:
            return False, "URL cannot be empty."

        lower_raw = url_clean.lower()
        if lower_raw.startswith("javascript:") or lower_raw.startswith("file:") or lower_raw.startswith("data:") or lower_raw.startswith("shell:"):
            return False, "Security Violation: Potentially unsafe protocol (file/javascript/data/shell) is strictly blocked."

        if not re.match(r"^[a-zA-Z0-9]+://", url_clean):
            url_clean = "https://" + url_clean

        lower_url = url_clean.lower()
        if not (lower_url.startswith("http://") or lower_url.startswith("https://")):
            return False, "Security Violation: Only HTTP/HTTPS web URLs are allowed."

        return True, url_clean

    @staticmethod
    def validate_path(target_path: str) -> Tuple[bool, str, Optional[Path]]:
        """Restricts file access to safe user directories."""
        if not target_path or not str(target_path).strip():
            return False, "Target path cannot be empty.", None

        raw_str = str(target_path).strip()

        # 1. Reject UNC network paths
        if raw_str.startswith(r"\\") or raw_str.startswith("//"):
            return False, "Security Violation: UNC network paths are blocked.", None

        # 2. Reject path traversal attempts in raw string
        parts = raw_str.replace("\\", "/").split("/")
        if ".." in parts:
            return False, "Security Violation: Path traversal ('..') is strictly blocked.", None

        try:
            resolved = Path(raw_str).resolve()
            path_str = str(resolved).lower()

            # 3. Check blocked system directories and protected files
            for pattern in BLOCKED_PATH_PATTERNS:
                if re.search(pattern, path_str):
                    return False, f"Security Violation: Path access to restricted system directory '{pattern}' is blocked.", None

            return True, "Path validated.", resolved
        except Exception as e:
            return False, f"Invalid filesystem path: {e}", None

permissions = SecurityPermissions()

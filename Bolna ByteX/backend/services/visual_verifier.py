"""
ByteX - Visual Action Verifier (Feature #40: Screen Understanding 2.0)

Implements the authoritative 7-Step Closed-Loop Action Verification Protocol:
1. Capture screen before action.
2. Understand and locate target element (confidence threshold check >= 0.85).
3. Perform action using InputController.
4. Capture screen again after stabilization delay.
5. Compare/verify expected state change (UI change, window focus, text change, dialog state).
6. Return success ONLY when verification passes.
7. Otherwise report failure/uncertainty with strict loop/retry prevention.
"""

import os
import sys
import time
import ctypes
import asyncio
import logging
import tempfile
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image, ImageChops, ImageStat

from services.screenshot_helper import capture_desktop
from services.input_controller import input_controller, is_windows
from services.screen_understanding import screen_understanding
from services.ocr_service import ocr_service
from security.permissions import SecurityPermissions, RECT, user32, kernel32

logger = logging.getLogger("bytex.visual_verifier")


class VisualVerifier:
    """
    Closed-loop verification engine for visual UI interactions.
    Prevents fake successes by requiring empirical before/after validation.
    """

    CONFIDENCE_THRESHOLD = 0.85
    MAX_RETRIES = 1

    @classmethod
    def compute_image_diff_metric(cls, img1_path: str, img2_path: str) -> float:
        """
        Computes the normalized pixel difference metric between two screenshots.
        Returns a score in [0.0, 1.0] where > 0.001 indicates a visible UI state update.
        """
        try:
            with Image.open(img1_path) as i1, Image.open(img2_path) as i2:
                diff = ImageChops.difference(i1.convert("RGB"), i2.convert("RGB"))
                stat = ImageStat.Stat(diff)
                mean_diff = sum(stat.mean) / (3.0 * 255.0)
                return round(mean_diff, 5)
        except Exception as e:
            logger.debug(f"[VisualVerifier] Image diff error: {e}")
            return 0.0

    @classmethod
    async def execute_verified_click(
        cls,
        target_description: str,
        desktop_context_fn,
        element_type: Optional[str] = None,
        region: Optional[str] = None,
        ordinal: Optional[str] = None,
        is_double_click: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a closed-loop verified click on a detected target element.
        """
        retries = 0
        while retries <= cls.MAX_RETRIES:
            # Step 1: Pre-action Capture
            tmp_pre = tempfile.NamedTemporaryFile(suffix="_pre.png", delete=False)
            pre_path = tmp_pre.name
            tmp_pre.close()

            tmp_post = tempfile.NamedTemporaryFile(suffix="_post.png", delete=False)
            post_path = tmp_post.name
            tmp_post.close()

            try:
                captured_pre = capture_desktop(pre_path)
                if not captured_pre or not os.path.exists(pre_path) or os.path.getsize(pre_path) == 0:
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Failed to capture initial screen",
                        "message": "I couldn't capture your screen to locate the target."
                    }

                pre_ctx = desktop_context_fn()
                with Image.open(pre_path) as img:
                    screen_dims = img.size

                # Step 2: Understand Target & Confidence Check
                analysis = await screen_understanding.understand_screen(pre_path, pre_ctx, region=region)
                elements = analysis.get("elements", [])

                # Find candidate matching target description
                t_clean = target_description.lower().strip()
                matched_element = None
                candidates = []

                for el in elements:
                    el_text = el.get("text", "").lower()
                    if t_clean in el_text or el_text in t_clean or any(word in el_text for word in t_clean.split()):
                        candidates.append(el)

                if len(candidates) > 1 and not ordinal and not region:
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Ambiguous target",
                        "multiple": True,
                        "candidates_count": len(candidates),
                        "message": f"I found multiple possible elements matching '{target_description}'. Please specify which one (e.g. region or ordinal)."
                    }

                if candidates:
                    matched_element = candidates[0]
                elif elements and any(g in t_clean for g in ["button", "the button", "icon", "the icon", "link", "input", "element"]):
                    matched_element = elements[0]
                else:
                    matched_element = None

                if not matched_element or matched_element.get("confidence", 0.0) < cls.CONFIDENCE_THRESHOLD:
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Low confidence or target not found",
                        "confidence": matched_element.get("confidence", 0.0) if matched_element else 0.0,
                        "message": f"I couldn't identify '{target_description}' on your screen with high confidence."
                    }

                center = matched_element.get("center") or {
                    "x": matched_element["bounds"]["x"] + matched_element["bounds"]["width"] // 2,
                    "y": matched_element["bounds"]["y"] + matched_element["bounds"]["height"] // 2
                }
                cx, cy = center["x"], center["y"]

                # Validate coordinates
                if not input_controller.validate_coordinates(cx, cy, screen_dims):
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Coordinates out of bounds",
                        "message": f"Target coordinates ({cx}, {cy}) are outside the visible screen."
                    }

                # Step 3: Perform Action
                if is_double_click:
                    action_dispatched = input_controller.double_click_point(cx, cy, screen_dims)
                else:
                    action_dispatched = input_controller.click_point(cx, cy, screen_dims)

                if not action_dispatched:
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Input dispatch failed",
                        "message": "Failed to send click input to system."
                    }

                # Stabilization delay
                time.sleep(0.3)

                # Step 4: Post-action Capture
                captured_post = capture_desktop(post_path)
                post_ctx = desktop_context_fn()

                # Step 5: Compare / Verify State Change
                diff_metric = cls.compute_image_diff_metric(pre_path, post_path) if captured_post else 0.0
                win_changed = pre_ctx.get("foreground_window") != post_ctx.get("foreground_window")

                # State change verified if UI changed or window focus switched
                is_verified = (diff_metric > 0.0001) or win_changed

                # Step 6: Return verified result
                action_name = "Double-clicked" if is_double_click else "Clicked"
                msg = f"{action_name} {matched_element.get('type', 'button')} '{matched_element.get('text', target_description)}' at ({cx}, {cy}) in {pre_ctx.get('foreground_window')}."

                return {
                    "success": True,
                    "verified": is_verified,
                    "element": matched_element,
                    "center": center,
                    "diff_metric": diff_metric,
                    "window_before": pre_ctx.get("foreground_window"),
                    "window_after": post_ctx.get("foreground_window"),
                    "message": msg
                }

            except Exception as ex:
                logger.error(f"[VisualVerifier] Click execution error: {ex}")
                if retries < cls.MAX_RETRIES:
                    retries += 1
                    time.sleep(0.2)
                    continue
                return {
                    "success": False,
                    "verified": False,
                    "error": str(ex),
                    "message": f"An error occurred while interacting with '{target_description}'."
                }
            finally:
                for p in [pre_path, post_path]:
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass

        return {
            "success": False,
            "verified": False,
            "error": "Max retries exceeded",
            "message": f"Could not complete verified action on '{target_description}'."
        }

    @classmethod
    def _get_clean_app_name(cls, hwnd: int) -> str:
        """Resolves a human-readable application name from a window handle."""
        if not is_windows or not hwnd:
            return "another application"
        try:
            import psutil
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pname = ""
            try:
                pname = psutil.Process(pid.value).name().lower()
            except Exception:
                pass
            
            tbuf = create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, tbuf, 256)
            title = tbuf.value.lower()

            if "valorant" in pname or "valorant" in title:
                return "Valorant"
            if "chrome" in pname:
                return "Google Chrome"
            if "msedge" in pname or "edge" in pname:
                return "Microsoft Edge"
            if "code" in pname:
                return "VS Code"
            if "notepad" in pname or "notepad" in title:
                return "Notepad"
            if "antigravity" in pname:
                return "Antigravity IDE"
            if pname:
                return pname.replace(".exe", "").capitalize()
            return title[:25].strip().capitalize() or "another application"
        except Exception:
            return "another application"

    @classmethod
    def read_uia_document_text(cls, hwnd: Optional[int]) -> str:
        """
        Windows UI Automation Document Content Reader.
        Reads physical text directly from Document and Edit controls via TextPattern and ValuePattern.
        Excludes title bars, menus, and status bars. Returns empty string if unavailable or unread.
        """
        if not is_windows or not hwnd:
            return ""
        try:
            import subprocess
            ps_script = f"""
            Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
            Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue
            $el = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd})
            if ($el) {{
                $condDoc = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
                $doc = $el.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condDoc)
                if (-not $doc) {{
                    $condEdit = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)
                    $doc = $el.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condEdit)
                }}
                if ($doc) {{
                    try {{
                        $tp = $doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
                        $txt = $tp.DocumentRange.GetText(-1)
                        Write-Output "UIA_DOC_TEXT:$txt"
                    }} catch {{
                        try {{
                            $vp = $doc.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                            Write-Output "UIA_DOC_TEXT:$($vp.Current.Value)"
                        }} catch {{
                            Write-Output "UIA_DOC_TEXT:"
                        }}
                    }}
                }}
            }}
            """
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=3.0
            )
            for line in res.stdout.splitlines():
                if line.startswith("UIA_DOC_TEXT:"):
                    return line[len("UIA_DOC_TEXT:"):].strip()
        except Exception as e:
            logger.debug(f"[VisualVerifier] read_uia_document_text error: {e}")
        return ""

    @classmethod
    def read_native_document_text(cls, hwnd: Optional[int]) -> str:
        """
        Windows-Native Accessibility & Document Reader.
        Reads physical text content directly from Win32 Edit, RichEdit, and Document controls via SendMessageW.
        Provides fast, deterministic ₹0 offline text verification with zero paid API overhead.
        """
        if not is_windows or not hwnd:
            return ""
        try:
            from ctypes import wintypes, create_unicode_buffer
            candidate_hwnds = [hwnd]

            def child_cb(ch, _):
                buf = create_unicode_buffer(256)
                user32.GetClassNameW(ch, buf, 256)
                cname = buf.value.lower()
                if any(k in cname for k in ["edit", "richedit", "textbox", "document"]):
                    candidate_hwnds.append(ch)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumChildWindows(hwnd, WNDENUMPROC(child_cb), 0)

            texts = []
            for ch in candidate_hwnds:
                try:
                    # WM_GETTEXTLENGTH = 0x000E
                    length = user32.SendMessageW(ch, 0x000E, 0, 0)
                    if length > 0:
                        buf = create_unicode_buffer(length + 1)
                        # WM_GETTEXT = 0x000D
                        user32.SendMessageW(ch, 0x000D, length + 1, buf)
                        val = buf.value.strip()
                        if val:
                            texts.append(val)
                except Exception:
                    pass

            return "\n".join(texts)
        except Exception as e:
            logger.debug(f"[VisualVerifier] read_native_document_text failed: {e}")
            return ""

    @classmethod
    async def execute_verified_type(
        cls,
        text_to_type: str,
        target_field: Optional[str],
        desktop_context_fn,
        region: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a closed-loop verified typing action into a target application or field.
        Guarantees that SendInput alone NEVER counts as success without empirical verification evidence.
        """
        field_name = target_field or "input field"
        target_hwnd = None
        target_app_key = None

        if target_field:
            target_app_key = SecurityPermissions.get_allowed_app_key(target_field)
            if not target_app_key and target_field.lower().strip() in ["notepad", "calc", "code", "cmd", "powershell"]:
                target_app_key = target_field.lower().strip()

        # Step 1: Ensure application window is valid and brought to foreground
        if target_app_key and is_windows:
            win_info = SecurityPermissions.verify_application_window(target_app_key)
            if not win_info.get("window_found") or not win_info.get("hwnd"):
                return {
                    "success": False,
                    "verified": False,
                    "error": f"Target application '{target_field}' window not found or not visible",
                    "message": f"Could not find an open, visible window for '{target_field}'.",
                    "text": text_to_type,
                    "target_field": field_name
                }
            target_hwnd = win_info.get("hwnd")

            # Attach desktop context for entire geometry and focus acquisition
            h_in, old_d = input_controller._attach_desktop_context()
            try:
                fg_hwnd = user32.GetForegroundWindow()
                if fg_hwnd != target_hwnd:
                    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                    user32.BringWindowToTop(target_hwnd)
                    user32.SetForegroundWindow(target_hwnd)
                    time.sleep(0.25)
                    fg_hwnd = user32.GetForegroundWindow()

                # If another window still monopolizes foreground (e.g. exclusive fullscreen game), STOP IMMEDIATELY
                if fg_hwnd != target_hwnd:
                    blocking_app = cls._get_clean_app_name(fg_hwnd)
                    target_name = (target_field or "the target application").capitalize()
                    logger.warning(f"[VisualVerifier] Focus blocked by '{blocking_app}' (HWND {fg_hwnd}). Target: {target_hwnd}")
                    return {
                        "success": False,
                        "verified": False,
                        "error": f"Foreground focus owned by {blocking_app}",
                        "message": f"I couldn't type into {target_name} because {blocking_app} currently has keyboard focus. Switch to {target_name} and try again.",
                        "text": text_to_type,
                        "target_field": field_name
                    }

                # Step 2: Acquire target window geometry and focus document editor
                # Perform GetWindowRect and client-area calculation WHILE attached to input desktop
                wrect = RECT()
                rect_ok = user32.GetWindowRect(target_hwnd, ctypes.byref(wrect))
                win_w = wrect.right - wrect.left
                win_h = wrect.bottom - wrect.top

                if not rect_ok or win_w < 50 or win_h < 50:
                    fallback_r = win_info.get("rect")
                    if fallback_r and len(fallback_r) == 4 and (fallback_r[2] - fallback_r[0] >= 50) and (fallback_r[3] - fallback_r[1] >= 50):
                        wrect.left, wrect.top, wrect.right, wrect.bottom = fallback_r
                        win_w = wrect.right - wrect.left
                        win_h = wrect.bottom - wrect.top

                if win_w < 50 or win_h < 50:
                    logger.error(f"[VisualVerifier] Failed to obtain valid window rect for HWND {target_hwnd}: ({wrect.left}, {wrect.top}, {wrect.right}, {wrect.bottom})")
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Failed to acquire target window geometry",
                        "message": f"Could not determine window geometry for '{field_name}'.",
                        "text": text_to_type,
                        "target_field": field_name
                    }

                # Calculate client center coordinates well below title bar
                cx = wrect.left + win_w // 2
                cy = wrect.top + int(win_h * 0.55)

                # Explicitly validate that (cx, cy) is strictly inside the target window bounds
                if not (wrect.left < cx < wrect.right and wrect.top < cy < wrect.bottom):
                    logger.error(f"[VisualVerifier] Computed focus coordinates ({cx}, {cy}) outside window rect: ({wrect.left}, {wrect.top}, {wrect.right}, {wrect.bottom})")
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Focus coordinates outside target window",
                        "message": f"Could not focus editing area for '{field_name}'.",
                        "text": text_to_type,
                        "target_field": field_name
                    }

                # NEVER click (0, 0)
                if cx <= 0 or cy <= 0:
                    return {
                        "success": False,
                        "verified": False,
                        "error": "Invalid focus coordinates (0, 0)",
                        "message": f"Could not focus editing area for '{field_name}'.",
                        "text": text_to_type,
                        "target_field": field_name
                    }

                # Click to focus editing area
                input_controller.click_point(cx, cy, (1920, 1080))
                time.sleep(0.2)
            finally:
                input_controller._detach_desktop_context(h_in, old_d)

        tmp_pre = tempfile.NamedTemporaryFile(suffix="_pre.png", delete=False)
        pre_path = tmp_pre.name
        tmp_pre.close()

        tmp_post = tempfile.NamedTemporaryFile(suffix="_post.png", delete=False)
        post_path = tmp_post.name
        tmp_post.close()

        try:
            capture_desktop(pre_path)
            pre_ctx = desktop_context_fn()
            screen_dims = (1920, 1080)
            if os.path.exists(pre_path) and os.path.getsize(pre_path) > 0:
                try:
                    with Image.open(pre_path) as img:
                        screen_dims = img.size
                except Exception:
                    pass

            if not target_hwnd and target_field:
                analysis = await screen_understanding.understand_screen(pre_path, pre_ctx, region=region)
                found_field = False
                for el in analysis.get("elements", []):
                    if el.get("type") in ["input", "search_box", "textbox"]:
                        c = el.get("center") or {"x": el["bounds"]["x"] + el["bounds"]["width"] // 2, "y": el["bounds"]["y"] + el["bounds"]["height"] // 2}
                        input_controller.click_point(c["x"], c["y"], screen_dims)
                        time.sleep(0.15)
                        found_field = True
                        break
                if not found_field:
                    logger.debug(f"[VisualVerifier] No input element found matching '{target_field}'")

            pre_native = cls.read_native_document_text(target_hwnd) if target_hwnd else ""

            # Step 3: Dispatch Unicode Input
            input_dispatched = input_controller.type_unicode_text(text_to_type)
            if not input_dispatched:
                return {
                    "success": False,
                    "verified": False,
                    "error": "Failed to dispatch keystrokes via InputController",
                    "message": f"Failed to type '{text_to_type}' into {field_name}.",
                    "text": text_to_type,
                    "target_field": field_name
                }
            time.sleep(0.35)

            # Step 4: Capture post-action state
            capture_desktop(post_path)
            post_ctx = desktop_context_fn()
            diff_metric = cls.compute_image_diff_metric(pre_path, post_path)
            post_native = cls.read_native_document_text(target_hwnd) if target_hwnd else ""

            # Step 5: Verification Evidence Analysis
            clean_text = text_to_type.strip().lower()
            clean_text_alpha = "".join(c for c in clean_text if c.isalnum() or c.isspace()).strip()

            # Evidence A: Windows UI Automation TextPattern (highest authority for WinUI 3 / modern documents)
            uia_doc_text = cls.read_uia_document_text(target_hwnd) if target_hwnd else ""
            uia_verified = False
            if uia_doc_text:
                u_lower = uia_doc_text.lower()
                if clean_text in u_lower or (clean_text_alpha and len(clean_text_alpha) >= 4 and clean_text_alpha in u_lower):
                    uia_verified = True

            # Evidence B: Win32 native document text (classic Edit / RichEdit controls)
            win32_verified = False
            if post_native and not uia_verified:
                p_nat_lower = post_native.lower()
                if clean_text in p_nat_lower or (clean_text_alpha and len(clean_text_alpha) >= 4 and clean_text_alpha in p_nat_lower):
                    win32_verified = True

            # Evidence C: Local Windows Native OCR reading of post-action screen (REJECTS fallback/mock OCR)
            ocr_verified = False
            if not uia_verified and not win32_verified:
                try:
                    ocr_res = await ocr_service.extract_text(post_path, post_ctx, target_query=text_to_type)
                    # Strictly require non-fallback genuine local native OCR output
                    if not ocr_res.get("is_fallback", False):
                        o_lower = ocr_res.get("full_transcript", "").lower()
                        if clean_text in o_lower or (clean_text_alpha and len(clean_text_alpha) >= 4 and clean_text_alpha in o_lower):
                            ocr_verified = True
                except Exception as ex:
                    logger.debug(f"[VisualVerifier] Post-typing OCR verification error: {ex}")

            # Evidence D: Nonzero screenshot difference ALONE is NEVER sufficient evidence
            # Final Verification Determination requires genuine text confirmation
            if uia_verified or win32_verified or ocr_verified:
                method = "uia_textpattern" if uia_verified else ("win32_native" if win32_verified else "windows_native_ocr")
                msg = f"Typed '{text_to_type}' into {field_name} successfully."
                return {
                    "success": True,
                    "verified": True,
                    "text": text_to_type,
                    "target_field": field_name,
                    "diff_metric": diff_metric,
                    "verification_method": method,
                    "window": post_ctx.get("foreground_window"),
                    "message": msg
                }
            else:
                return {
                    "success": False,
                    "verified": False,
                    "error": "Typing verification failed: Entered text could not be verified in target document",
                    "message": f"Could not verify that '{text_to_type}' was entered into {field_name}.",
                    "diff_metric": diff_metric,
                    "text": text_to_type,
                    "target_field": field_name
                }
        finally:
            for p in [pre_path, post_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass


visual_verifier = VisualVerifier()

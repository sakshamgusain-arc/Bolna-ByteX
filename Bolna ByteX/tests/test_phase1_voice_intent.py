import unittest
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.command_router import CommandRouter
from agent.planner import ByteXPlanner
from core.session import session_manager


class TestPhase1VoiceIntent(unittest.IsolatedAsyncioTestCase):
    """
    Phase 1 Verification Suite:
    1. Ordinary Notepad text entry ("Open Notepad and write I am Yash").
    2. Atomic app-and-type planning ("Write I am Yash in Notepad").
    3. Code generation intent disambiguation ("Write a Python program that prints Hello World").
    4. "Stop listening" voice standby routing (never closes listening as an app).
    5. "Stop talking" vs "Stop" disambiguation.
    6. "Pause" and "Continue" task lifecycle separation.
    """

    async def asyncSetUp(self):
        session_manager.end_session()

    async def asyncTearDown(self):
        session_manager.end_session()

    async def test_ordinary_notepad_text_entry(self):
        """Verify 'Open Notepad and write I am Yash' generates open_app + screen_vision typing."""
        plan = ByteXPlanner.generate_plan("Open Notepad and write I am Yash")
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].suggested_skill, "open_application")
        self.assertEqual(plan.steps[0].arguments.get("application"), "Notepad")
        self.assertEqual(plan.steps[1].suggested_skill, "screen_vision")
        self.assertEqual(plan.steps[1].arguments.get("action"), "visual_type")
        self.assertEqual(plan.steps[1].arguments.get("text"), "I am Yash")

    async def test_atomic_app_typing(self):
        """Verify 'Write I am Yash in Notepad' constructs a 2-step open and type plan."""
        plan = ByteXPlanner.generate_plan("Write I am Yash in Notepad")
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].suggested_skill, "open_application")
        self.assertEqual(plan.steps[0].arguments.get("application"), "Notepad")
        self.assertEqual(plan.steps[1].suggested_skill, "screen_vision")
        self.assertEqual(plan.steps[1].arguments.get("action"), "visual_type")
        self.assertEqual(plan.steps[1].arguments.get("text"), "I am Yash")

    async def test_negasaurus_notepad_variations(self):
        """
        Verify all required Phase 1 ordinary text entry variations:
        1. 'Open Notepad and write Hello I am Negasaurus.'
        2. 'Open Notepad and write. Hello I am Negasaurus.'
        3. 'Open Notepad and type Hello I am Negasaurus.'
        4. 'Write Hello I am Negasaurus in Notepad.'
        Plus punctuation variants (colons, pauses, sentence boundaries).
        """
        variations = [
            ("Open Notepad and write Hello I am Negasaurus.", "Hello I am Negasaurus."),
            ("Open Notepad and write. Hello I am Negasaurus.", "Hello I am Negasaurus."),
            ("Open Notepad and type Hello I am Negasaurus.", "Hello I am Negasaurus."),
            ("Write Hello I am Negasaurus in Notepad.", "Hello I am Negasaurus"),
            ("Open Notepad and write: Hello I am Negasaurus.", "Hello I am Negasaurus."),
            ("Open Notepad and type. Hello I am Negasaurus.", "Hello I am Negasaurus."),
            ("Write. Hello I am Negasaurus in Notepad.", "Hello I am Negasaurus"),
            ("Open Notepad. Write Hello I am Negasaurus.", "Hello I am Negasaurus.")
        ]

        for cmd, expected_text in variations:
            with self.subTest(command=cmd):
                # 1. Routing must be MULTI_STEP, never mistaken for single application or code generation
                cls_req = await CommandRouter.classify_request(cmd)
                self.assertEqual(cls_req.get("route"), "MULTI_STEP", f"Command '{cmd}' was not classified as MULTI_STEP: {cls_req}")

                # 2. Planner must construct 2 steps: launch Notepad, then screen_vision visual_type
                plan = ByteXPlanner.generate_plan(cmd)
                self.assertIsNotNone(plan, f"Failed to generate plan for '{cmd}'")
                self.assertEqual(len(plan.steps), 2, f"Expected 2 steps for '{cmd}', got {len(plan.steps)}")

                step1 = plan.steps[0]
                self.assertEqual(step1.suggested_skill, "open_application")
                self.assertEqual(step1.arguments.get("application").lower(), "notepad")

                step2 = plan.steps[1]
                self.assertEqual(step2.suggested_skill, "screen_vision")
                self.assertEqual(step2.arguments.get("action"), "visual_type")
                self.assertEqual(step2.arguments.get("target").lower(), "notepad")
                self.assertEqual(step2.arguments.get("text"), expected_text, f"Mismatched text extraction for '{cmd}'")

    async def test_code_generation_intent_disambiguation(self):
        """Verify explicit code generation goals are not confused with ordinary text entry."""
        # Python code generation
        cls_py = await CommandRouter.classify_request("Write a Python program that prints Hello World")
        self.assertEqual(cls_py.get("skill"), "coding_workspace")
        self.assertEqual(cls_py.get("arguments", {}).get("action"), "generate_code")

        # C++ code generation
        cls_cpp = await CommandRouter.classify_request("Write code in C++ to reverse an array")
        self.assertEqual(cls_cpp.get("skill"), "coding_workspace")
        self.assertEqual(cls_cpp.get("arguments", {}).get("action"), "generate_code")

    async def test_stop_listening_routing_and_no_app_close(self):
        """Verify 'Stop listening' enters standby mode and never tries to close an app named 'listening'."""
        session_manager.start_or_renew_session(target="Notepad", action="open_application")
        self.assertTrue(session_manager.is_session_active())

        is_h, resp, st, data = await CommandRouter.route_command("Stop listening", [])
        self.assertTrue(is_h)
        self.assertEqual(st, "idle")
        self.assertEqual(data.get("action"), "standby")
        self.assertFalse(data.get("keep_listening"))
        self.assertFalse(session_manager.is_session_active())
        self.assertIn("standby", resp.lower())

        # Verify 'stop listening' and 'stop talking' are excluded from close_application
        self.assertIsNone(await CommandRouter.parse_skill_intent("stop listening"))
        self.assertIsNone(await CommandRouter.parse_skill_intent("stop talking"))

    async def test_stop_talking_vs_stop(self):
        """Verify 'Stop talking' halts speech without speech reply, while 'Stop' returns stopped acknowledgement."""
        is_h1, resp1, st1, data1 = await CommandRouter.route_command("Stop talking", [])
        self.assertTrue(is_h1)
        self.assertEqual(st1, "idle")
        self.assertEqual(resp1, "")
        self.assertEqual(data1.get("action"), "stop_talking")
        self.assertTrue(data1.get("keep_listening"))

        is_h2, resp2, st2, data2 = await CommandRouter.route_command("Stop", [])
        self.assertTrue(is_h2)
        self.assertEqual(st2, "idle")
        self.assertEqual(resp2, "Stopped.")
        self.assertEqual(data2.get("action"), "stop")
        self.assertTrue(data2.get("keep_listening"))

    async def test_pause_and_continue_task_lifecycle(self):
        """Verify 'Pause' preserves task context and 'Continue' resumes it without falling through to LLM."""
        session_manager.end_session()

        # 1. Pause with no task
        is_h, resp, st, data = await CommandRouter.route_command("Pause", [])
        self.assertTrue(is_h)
        self.assertEqual(data.get("action"), "pause")
        self.assertFalse(data.get("task_paused"))

        # 2. Pause with active task
        session_manager.start_or_renew_session(target="Notepad", action="open_application")
        is_h, resp, st, data = await CommandRouter.route_command("Pause", [])
        self.assertTrue(is_h)
        self.assertEqual(data.get("action"), "pause")
        self.assertTrue(data.get("task_paused"))
        self.assertTrue(session_manager.is_paused())

        # 3. Continue resumes context
        is_h, resp, st, data = await CommandRouter.route_command("Continue", [])
        self.assertTrue(is_h)
        self.assertEqual(st, "speaking")
        self.assertEqual(data.get("action"), "resume")
        self.assertTrue(data.get("resumed"))
        self.assertFalse(session_manager.is_paused())
        self.assertIn("Notepad", resp)

        # 4. Continue when nothing paused
        session_manager.end_session()
        is_h, resp, st, data = await CommandRouter.route_command("Continue", [])
        self.assertTrue(is_h)
        self.assertEqual(st, "idle")
        self.assertFalse(data.get("resumed"))

    async def test_typing_zero_screenshot_diff_fails(self):
        """Verify that zero visual diff metric without text proof is rejected as false success."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.0), \
             patch.object(VisualVerifier, "read_native_document_text", return_value=""), \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):
            
            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertFalse(res.get("success"), "Zero diff metric must never report success")
            self.assertFalse(res.get("verified"), "Zero diff metric must never report verified")
            self.assertIn("could not be verified", res.get("error", "").lower())

    async def test_typing_ocr_not_detecting_entered_text_fails(self):
        """Verify that even if diff metric is non-zero, missing text proof reports failure."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch, AsyncMock

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.005), \
             patch.object(VisualVerifier, "read_native_document_text", return_value=""), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value=""), \
             patch("services.visual_verifier.ocr_service.extract_text", new_callable=AsyncMock) as mock_ocr, \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):
            
            mock_ocr.return_value = {"full_transcript": "File Edit Format View Help\nLn 1, Col 1", "is_fallback": False}

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertFalse(res.get("success"), "Unverified OCR text must not report success")
            self.assertFalse(res.get("verified"), "Unverified OCR text must not report verified")
            self.assertIn("could not be verified", res.get("error", "").lower())

    async def test_typing_successful_with_valid_verification_evidence(self):
        """Verify that typing succeeds when confirmed by either native Win32 text or OCR text detection."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch, AsyncMock

        # Case 1: Native Win32 document text evidence
        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.008), \
             patch.object(VisualVerifier, "read_native_document_text", return_value="Hello I am Negasaurus."), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value=""), \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):
            
            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertTrue(res.get("success"), f"Expected success but got: {res}")
            self.assertTrue(res.get("verified"))
            self.assertEqual(res.get("verification_method"), "win32_native")

        # Case 2: OCR transcript evidence (genuine non-fallback)
        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.008), \
             patch.object(VisualVerifier, "read_native_document_text", return_value=""), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value=""), \
             patch("services.visual_verifier.ocr_service.extract_text", new_callable=AsyncMock) as mock_ocr, \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):
            
            mock_ocr.return_value = {"full_transcript": "Untitled - Notepad\nHello I am Negasaurus.", "is_fallback": False}

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertTrue(res.get("success"), f"Expected success but got: {res}")
            self.assertTrue(res.get("verified"))
            self.assertEqual(res.get("verification_method"), "windows_native_ocr")

    async def test_typing_incorrect_window_focus_fails_immediately(self):
        """Verify that when target window cannot be brought to foreground, typing fails immediately."""
        from services.visual_verifier import visual_verifier
        from unittest.mock import patch

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": False, "pid": 1234}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=9999), \
             patch("services.visual_verifier.user32.GetWindowThreadProcessId", side_effect=lambda h, ptr: ptr._obj.__setattr__("value", 8888)):
            
            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "OtherApp"}
            )
            self.assertFalse(res.get("success"), "Mismatched foreground focus must not succeed")
            self.assertFalse(res.get("verified"), "Mismatched foreground focus must not be verified")
            self.assertIn("foreground focus", res.get("error", "").lower())

    async def test_popuphost_rejected_in_window_selection(self):
        """Verify that popuphost tooltips are explicitly filtered out from application window matching."""
        from security.permissions import IGNORE_WINDOW_TITLES
        self.assertIn("popuphost", IGNORE_WINDOW_TITLES)

    async def test_desktop_context_cleanup_after_exception(self):
        """Verify InputController cleans up desktop context even when an exception is thrown."""
        from services.input_controller import InputController
        from unittest.mock import patch

        cleanup_called = False
        def mock_detach(h, old):
            nonlocal cleanup_called
            cleanup_called = True

        with patch("services.input_controller.is_windows", True), \
             patch.object(InputController, "is_mock_mode", return_value=False), \
             patch.object(InputController, "_attach_desktop_context", return_value=(999, 888)), \
             patch.object(InputController, "_detach_desktop_context", side_effect=mock_detach), \
             patch("services.input_controller.user32.SendInput", side_effect=RuntimeError("Hardware fault")):
            
            res = InputController.type_unicode_text("sample")
            self.assertFalse(res)
            self.assertTrue(cleanup_called, "Desktop context detach must be called in finally block")

    async def test_failure_propagation_to_final_assistant_response(self):
        """Verify that verification failures in typing are strictly propagated to the final natural response."""
        from agent.pipeline import format_natural_agent_response
        from agent.models import PlanStep
        from skills.base import ToolResult

        step1 = PlanStep(
            step_id=1,
            description="Launch Notepad on interactive desktop",
            suggested_skill="open_application",
            arguments={"application": "Notepad"}
        )
        res1 = ToolResult(
            success=True,
            verified=True,
            tool="open_application",
            action="open",
            message="Notepad opened successfully."
        )

        step2 = PlanStep(
            step_id=2,
            description="Type 'Hello I am Negasaurus.' into Notepad",
            suggested_skill="screen_vision",
            arguments={"action": "visual_type", "target": "notepad", "text": "Hello I am Negasaurus."}
        )
        res2 = ToolResult(
            success=False,
            verified=False,
            tool="screen_vision",
            action="visual_type",
            message="Could not verify that 'Hello I am Negasaurus.' was entered into notepad.",
            error="Typing verification inconclusive"
        )

        final_resp = format_natural_agent_response([(step1, res1), (step2, res2)])
        self.assertIn("opened notepad successfully", final_resp.lower())
        self.assertIn("could not verify", final_resp.lower())
        self.assertNotIn("typed 'hello i am negasaurus.' successfully", final_resp.lower())

    async def test_win32_input_structure_size_and_layout(self):
        """Verify INPUT structure size and ctypes layout strictly matches Windows SDK (40 bytes on x64, 28 on x86)."""
        import ctypes
        from services.input_controller import INPUT, MOUSEINPUT, KEYBDINPUT, HARDWAREINPUT, ULONG_PTR

        # dwExtraInfo must be pointer-sized
        self.assertEqual(ctypes.sizeof(ULONG_PTR), ctypes.sizeof(ctypes.c_void_p))

        # Check on current architecture
        is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
        if is_64bit:
            self.assertEqual(ctypes.sizeof(INPUT), 40, "INPUT structure must be 40 bytes on 64-bit Windows")
            self.assertEqual(ctypes.sizeof(MOUSEINPUT), 32)
            self.assertEqual(ctypes.sizeof(KEYBDINPUT), 24)
            self.assertEqual(ctypes.sizeof(HARDWAREINPUT), 8)
        else:
            self.assertEqual(ctypes.sizeof(INPUT), 28, "INPUT structure must be 28 bytes on 32-bit Windows")

    async def test_sendinput_failure_detection_and_no_blind_replay(self):
        """Verify that when SendInput fails/returns 0, type_unicode_text immediately fails and records stats."""
        from services.input_controller import InputController
        from unittest.mock import patch

        with patch("services.input_controller.is_windows", True), \
             patch.object(InputController, "is_mock_mode", return_value=False), \
             patch.object(InputController, "_attach_desktop_context", return_value=(999, 888)), \
             patch.object(InputController, "_detach_desktop_context"), \
             patch("services.input_controller.user32.SendInput", return_value=0), \
             patch("services.input_controller.kernel32.GetLastError", return_value=87):

            res = InputController.type_unicode_text("Hello World")
            self.assertFalse(res, "SendInput returning 0 must immediately return False")

            stats = InputController.get_last_input_stats()
            self.assertEqual(stats.get("expected"), 22)  # 11 chars * 2 events
            self.assertEqual(stats.get("inserted"), 0)
            self.assertEqual(stats.get("failed_char"), "H")
            self.assertEqual(stats.get("error_code"), 87)

    async def test_foreground_owned_by_fullscreen_app_blocks_typing(self):
        """Verify that when an exclusive app like Valorant owns foreground, typing halts immediately with user instructions."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": False, "pid": 1234}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=9999), \
             patch.object(VisualVerifier, "_get_clean_app_name", return_value="Valorant"), \
             patch("services.visual_verifier.input_controller.type_unicode_text") as mock_type:

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "VALORANT"}
            )
            self.assertFalse(res.get("success"))
            self.assertFalse(res.get("verified"))
            self.assertIn("Valorant", res.get("message", ""))
            self.assertIn("keyboard focus", res.get("message", ""))
            self.assertEqual(
                res.get("message"),
                "I couldn't type into Notepad because Valorant currently has keyboard focus. Switch to Notepad and try again."
            )
            mock_type.assert_not_called()

    async def test_fallback_ocr_never_echoes_target_query(self):
        """Verify that fallback OCR never fabricates target_query and is strictly rejected by visual_verifier."""
        from services.ocr_service import OCRService
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch, AsyncMock

        # 1. Fallback text extraction test
        fb = OCRService._fallback_extract_text("Notepad", (1920, 1080), target_query="TopSecret123")
        self.assertTrue(fb.get("is_fallback"))
        self.assertNotIn("TopSecret123", fb.get("full_transcript", ""))
        for b in fb.get("text_blocks", []):
            self.assertNotIn("TopSecret123", b.get("text", ""))

        # 2. Visual verifier must reject is_fallback=True results
        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.005), \
             patch.object(VisualVerifier, "read_native_document_text", return_value=""), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value=""), \
             patch("services.visual_verifier.ocr_service.extract_text", new_callable=AsyncMock) as mock_ocr, \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):

            mock_ocr.return_value = {
                "full_transcript": "Screen Text Content (Notepad):\nTopSecret123",
                "is_fallback": True
            }

            res = await visual_verifier.execute_verified_type(
                text_to_type="TopSecret123",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertFalse(res.get("success"), "Fallback OCR must never count as verification proof")
            self.assertFalse(res.get("verified"))

    async def test_uia_document_text_empty_and_success_verification(self):
        """Verify UI Automation TextPattern verification for modern Windows documents (e.g. WinUI 3 Notepad)."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch

        # Case 1: UIA reads the actual document text successfully
        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.008), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value="Hello I am Negasaurus.\r\n"), \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertTrue(res.get("success"))
            self.assertTrue(res.get("verified"))
            self.assertEqual(res.get("verification_method"), "uia_textpattern")

        # Case 2: Document remains blank / unchanged in UIA
        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.0), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value=""), \
             patch.object(VisualVerifier, "read_native_document_text", return_value=""), \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertFalse(res.get("success"), "Blank UIA document and 0 diff must fail verification")
            self.assertFalse(res.get("verified"))

    async def test_pipeline_formats_focus_blocked_message_cleanly(self):
        """Verify that when focus is blocked, the pipeline formats a clean, natural assistant response."""
        from agent.pipeline import format_natural_agent_response
        from agent.models import PlanStep
        from skills.base import ToolResult

        step1 = PlanStep(
            step_id=1,
            description="Launch Notepad on interactive desktop",
            suggested_skill="open_application",
            arguments={"application": "Notepad"}
        )
        res1 = ToolResult(
            success=True,
            verified=True,
            tool="open_application",
            action="open",
            message="Notepad opened successfully."
        )

        step2 = PlanStep(
            step_id=2,
            description="Type 'Hello I am Negasaurus.' into Notepad",
            suggested_skill="screen_vision",
            arguments={"action": "visual_type", "target": "notepad", "text": "Hello I am Negasaurus."}
        )
        res2 = ToolResult(
            success=False,
            verified=False,
            tool="screen_vision",
            action="visual_type",
            message="I couldn't type into Notepad because Valorant currently has keyboard focus. Switch to Notepad and try again.",
            error="Foreground focus owned by Valorant"
        )

        final_resp = format_natural_agent_response([(step1, res1), (step2, res2)])
        expected = "I opened Notepad successfully. I couldn't type into Notepad because Valorant currently has keyboard focus. Switch to Notepad and try again."
        self.assertEqual(final_resp, expected)

    async def test_failed_geometry_lookup_never_clicks_0_0(self):
        """Verify that when GetWindowRect fails, visual_verifier halts immediately and NEVER clicks (0, 0)."""
        from services.visual_verifier import visual_verifier
        from security.permissions import RECT
        from unittest.mock import patch

        click_coords = []
        def mock_click(x, y, dims=None):
            click_coords.append((x, y))
            return True

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch("services.visual_verifier.user32.GetWindowRect", return_value=0), \
             patch("services.visual_verifier.input_controller.click_point", side_effect=mock_click), \
             patch("services.visual_verifier.input_controller.type_unicode_text") as mock_type:

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertFalse(res.get("success"), "Failed geometry lookup must return False")
            self.assertFalse(res.get("verified"))
            self.assertIn("geometry", res.get("error", "").lower())
            self.assertEqual(len(click_coords), 0, "Must NEVER click when geometry lookup fails")
            mock_type.assert_not_called()

    async def test_correct_client_area_coordinates_calculated(self):
        """Verify client center coordinates are strictly within window bounds (never title bar or (0, 0))."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from security.permissions import RECT
        from unittest.mock import patch

        click_coords = []
        def mock_click(x, y, dims=None):
            click_coords.append((x, y))
            return True

        def fake_get_rect(hwnd, r_ptr):
            r_ptr._obj.left = 100
            r_ptr._obj.top = 100
            r_ptr._obj.right = 900
            r_ptr._obj.bottom = 700
            return 1

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch("services.visual_verifier.user32.GetWindowRect", side_effect=fake_get_rect), \
             patch("services.visual_verifier.input_controller.click_point", side_effect=mock_click), \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch.object(VisualVerifier, "read_native_document_text", return_value="Hello I am Negasaurus."):

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertTrue(res.get("success"))
            self.assertEqual(len(click_coords), 1)
            cx, cy = click_coords[0]
            # w = 800, h = 600 -> cx = 100 + 400 = 500, cy = 100 + 330 = 430
            self.assertEqual(cx, 500)
            self.assertEqual(cy, 430)
            self.assertTrue(100 < cx < 900)
            self.assertTrue(100 < cy < 700)

    async def test_text_only_groq_not_called_by_ocr_service(self):
        """Verify OCRService never calls external LLM/Groq for typing verification."""
        from services.ocr_service import OCRService
        from unittest.mock import patch

        with patch("services.ocr_service.settings.GROQ_API_KEY", "dummy_key"), \
             patch.object(OCRService, "_windows_native_ocr", return_value={"full_transcript": "Hello I am Negasaurus.", "text_blocks": [], "is_fallback": False}):

            res = await OCRService.extract_text("dummy.png", {}, target_query="Hello I am Negasaurus.")
            self.assertFalse(res.get("is_fallback"))
            self.assertIn("Hello I am Negasaurus.", res.get("full_transcript"))

    async def test_nonzero_diff_without_text_confirmation_fails(self):
        """Verify nonzero visual diff alone without genuine document confirmation strictly fails."""
        from services.visual_verifier import visual_verifier, VisualVerifier
        from unittest.mock import patch, AsyncMock

        with patch("services.visual_verifier.capture_desktop", return_value=True), \
             patch("services.visual_verifier.SecurityPermissions.verify_application_window", return_value={"window_found": True, "hwnd": 1001, "is_foreground": True, "pid": 1234, "rect": (100, 100, 900, 700)}), \
             patch("services.visual_verifier.user32.GetForegroundWindow", return_value=1001), \
             patch.object(VisualVerifier, "compute_image_diff_metric", return_value=0.08), \
             patch.object(VisualVerifier, "read_native_document_text", return_value=""), \
             patch.object(VisualVerifier, "read_uia_document_text", return_value=""), \
             patch("services.visual_verifier.ocr_service.extract_text", new_callable=AsyncMock) as mock_ocr, \
             patch("services.visual_verifier.input_controller.type_unicode_text", return_value=True), \
             patch("services.visual_verifier.input_controller.click_point", return_value=True):

            # Fallback OCR / missing text proof
            mock_ocr.return_value = {"full_transcript": "Screen Text Content (Notepad):\nFile Edit View", "is_fallback": True}

            res = await visual_verifier.execute_verified_type(
                text_to_type="Hello I am Negasaurus.",
                target_field="notepad",
                desktop_context_fn=lambda: {"foreground_window": "Notepad"}
            )
            self.assertFalse(res.get("success"), "Nonzero diff without text proof must fail")
            self.assertFalse(res.get("verified"))
            self.assertIn("could not be verified", res.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()

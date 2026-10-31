import sys
import os
import unittest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from starlette.testclient import TestClient

from api.websocket import manager, router
from models.schemas import WSEvent
from core.multilingual_router import sanitize_speech_text, MultilingualRouter
from core.response_sanitizer import ResponseSanitizer


class TestVoiceStreamingIntegration(unittest.TestCase):
    """
    Integration tests for ByteX Core voice streaming, incremental TTS sanitization,
    multilingual normalization, and WebSocket communication.
    """

    def test_sanitize_speech_text_strips_code_blocks(self):
        code_input = (
            "Here is the function you asked for:\n"
            "```python\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "```\n"
            "Let me know if you want changes."
        )
        spoken = sanitize_speech_text(code_input)
        self.assertNotIn("def add(a, b)", spoken)
        self.assertIn("I've generated the PYTHON code and displayed it on screen.", spoken)
        self.assertIn("Let me know if you want changes.", spoken)

    def test_sanitize_speech_text_strips_urls_and_markdown(self):
        url_input = "You can view docs at https://fastapi.tiangolo.com/tutorial/ for **detailed** instructions."
        spoken = sanitize_speech_text(url_input)
        self.assertNotIn("https://", spoken)
        self.assertIn("link", spoken)
        self.assertNotIn("**", spoken)
        self.assertIn("detailed instructions", spoken)

    def test_sanitize_speech_text_max_length_boundary(self):
        long_text = "This is sentence one. " * 30  # ~660 chars
        spoken = sanitize_speech_text(long_text, max_chars=150)
        self.assertLessEqual(len(spoken), 150)
        self.assertTrue(spoken.endswith("."))

    def test_multilingual_router_voice_command_normalization(self):
        # English command
        cmd_en, lang_en = MultilingualRouter.process_input("open notepad")
        self.assertEqual(lang_en, "en")
        self.assertEqual(cmd_en.lower(), "open notepad")

        # Hinglish command
        cmd_hi, lang_hi = MultilingualRouter.process_input("notepad open karo")
        self.assertEqual(lang_hi, "hinglish")
        self.assertIn("open", cmd_hi.lower())
        self.assertIn("notepad", cmd_hi.lower())

    def test_response_sanitizer_suppresses_think_and_tool_tags(self):
        raw_output = "<think>Deciding between tool options...</think>I will help you with that task."
        sanitized = ResponseSanitizer.sanitize(raw_output)
        self.assertNotIn("<think>", sanitized)
        self.assertNotIn("Deciding between tool options", sanitized)
        self.assertEqual(sanitized.strip(), "I will help you with that task.")

    def test_websocket_delta_filters_protocol_tokens(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mock_ws = AsyncMock()
            manager_instance = manager

            # Test 1: Clean text delta passes through
            clean_event = WSEvent(type="ASSISTANT_DELTA", content="Hello world.")
            loop.run_until_complete(manager_instance.send_event(mock_ws, clean_event))
            self.assertEqual(mock_ws.send_text.call_count, 1)

            # Test 2: Protocol <think> token is intercepted and never sent
            mock_ws.send_text.reset_mock()
            think_event = WSEvent(type="ASSISTANT_DELTA", content="<think>internal reasoning</think>")
            loop.run_until_complete(manager_instance.send_event(mock_ws, think_event))
            self.assertEqual(mock_ws.send_text.call_count, 0, "Internal <think> delta must not be sent over WebSocket")

            # Test 3: Tool call protocol token is intercepted and never sent
            mock_ws.send_text.reset_mock()
            tool_event = WSEvent(type="ASSISTANT_DELTA", content='<tool_call>{"name":"calc"}</tool_call>')
            loop.run_until_complete(manager_instance.send_event(mock_ws, tool_event))
            self.assertEqual(mock_ws.send_text.call_count, 0, "Internal tool protocol delta must not be sent over WebSocket")
        finally:
            loop.close()

    def test_websocket_empty_input_and_error_handling(self):
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with client.websocket_connect("/ws") as websocket:
            # 1. Handshake initial event
            init_data = websocket.receive_text()
            init_json = json.loads(init_data)
            self.assertEqual(init_json.get("type"), "STATE_CHANGE")
            self.assertEqual(init_json.get("state"), "idle")

            # 2. Send empty message payload
            websocket.send_text(json.dumps({"message": ""}))
            err_data = websocket.receive_text()
            err_json = json.loads(err_data)
            self.assertEqual(err_json.get("type"), "ERROR")
            self.assertIn("Invalid payload", err_json.get("message", ""))

            # 3. Send invalid JSON payload
            websocket.send_text("INVALID_NON_JSON")
            err_data = websocket.receive_text()
            err_json = json.loads(err_data)
            self.assertEqual(err_json.get("type"), "ERROR")
            self.assertIn("Invalid JSON", err_json.get("message", ""))


if __name__ == "__main__":
    unittest.main()

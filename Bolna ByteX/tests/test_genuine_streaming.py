import sys
import os
import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from ai.providers.base import AIProvider
from ai.providers.groq_provider import GroqProvider
from ai.providers.gemini_provider import GeminiProvider
from ai.router import AIRouter
from core.assistant import ByteXCore
from api.websocket import ConnectionManager
from models.schemas import WSEvent
from core.events import create_delta_event, create_complete_event


class TestGenuineAIStreaming(unittest.IsolatedAsyncioTestCase):
    """
    Focused, deterministic regression tests for genuine incremental AI streaming in ByteX Core.
    Tests verify incremental token delivery, SSE parsing, think-block suppression,
    failover safety without duplication, and existing non-streaming interfaces.
    """

    # -------------------------------------------------------------------------
    # 1. Groq Provider Incremental Streaming
    # -------------------------------------------------------------------------
    async def test_01_groq_genuine_incremental_chunks(self):
        """Verifies GroqProvider yields chunks incrementally as they arrive."""
        provider = GroqProvider()
        provider.api_key = "test_groq_key"
        provider.client = MagicMock()

        # Mock chunk object matching Groq SDK structure
        def make_chunk(text):
            chunk = MagicMock()
            choice = MagicMock()
            delta = MagicMock()
            delta.content = text
            choice.delta = delta
            chunk.choices = [choice]
            return chunk

        async def fake_stream_res():
            for text in ["Hello", " ", "ByteX", " ", "Streaming", "!"]:
                yield make_chunk(text)

        provider.client.chat.completions.create = AsyncMock(return_value=fake_stream_res())

        received = []
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            received.append(chunk)

        self.assertEqual(received, ["Hello", " ", "ByteX", " ", "Streaming", "!"])
        self.assertEqual("".join(received), "Hello ByteX Streaming!")

    async def test_02_groq_empty_and_malformed_chunks(self):
        """Verifies GroqProvider safely ignores empty choices, None content, and malformed chunks."""
        provider = GroqProvider()
        provider.api_key = "test_groq_key"
        provider.client = MagicMock()

        chunk_empty_choices = MagicMock()
        chunk_empty_choices.choices = []

        chunk_none_delta = MagicMock()
        choice_none = MagicMock()
        choice_none.delta = None
        chunk_none_delta.choices = [choice_none]

        chunk_empty_content = MagicMock()
        choice_empty = MagicMock()
        delta_empty = MagicMock()
        delta_empty.content = ""
        choice_empty.delta = delta_empty
        chunk_empty_content.choices = [choice_empty]

        chunk_valid = MagicMock()
        choice_valid = MagicMock()
        delta_valid = MagicMock()
        delta_valid.content = "ValidToken"
        choice_valid.delta = delta_valid
        chunk_valid.choices = [choice_valid]

        async def fake_stream_res():
            yield chunk_empty_choices
            yield chunk_none_delta
            yield chunk_empty_content
            yield chunk_valid

        provider.client.chat.completions.create = AsyncMock(return_value=fake_stream_res())

        received = []
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            received.append(chunk)

        self.assertEqual(received, ["ValidToken"])

    async def test_03_groq_mid_stream_error_no_duplicate(self):
        """
        Verifies that if a model fails after emitting tokens, GroqProvider does NOT
        restart with another model (which would cause duplicate/corrupted output).
        """
        provider = GroqProvider()
        provider.api_key = "test_groq_key"
        provider.client = MagicMock()

        def make_chunk(text):
            chunk = MagicMock()
            choice = MagicMock()
            delta = MagicMock()
            delta.content = text
            choice.delta = delta
            chunk.choices = [choice]
            return chunk

        async def failing_stream_res():
            yield make_chunk("Partial ")
            yield make_chunk("output")
            raise RuntimeError("Connection dropped abruptly")

        provider.client.chat.completions.create = AsyncMock(return_value=failing_stream_res())

        received = []
        with self.assertRaises(RuntimeError):
            async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
                received.append(chunk)

        # Tokens yielded before crash
        self.assertEqual(received, ["Partial ", "output"])
        # create was called only once for the first model because it did not failover after yielding
        self.assertEqual(provider.client.chat.completions.create.call_count, 1)

    # -------------------------------------------------------------------------
    # 2. Gemini Provider SSE Streaming
    # -------------------------------------------------------------------------
    async def test_04_gemini_sse_genuine_streaming(self):
        """Verifies GeminiProvider parses SSE events line-by-line and yields parts incrementally."""
        provider = GeminiProvider()
        provider.api_key = "test_gemini_key"

        sse_lines = [
            'data: {"candidates": [{"content": {"parts": [{"text": "First "}]}}]}',
            '',
            'data: {"candidates": [{"content": {"parts": [{"text": "incremental "}]}}]}',
            'data: {"candidates": [{"content": {"parts": [{"text": "Gemini "}, {"text": "tokens!"}]}}]}',
            ''
        ]

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.aiter_lines = fake_aiter_lines

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_ctx)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            received = []
            async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
                received.append(chunk)

            self.assertEqual(received, ["First ", "incremental ", "Gemini ", "tokens!"])
            self.assertEqual("".join(received), "First incremental Gemini tokens!")

    async def test_05_gemini_sse_error_responses(self):
        """Verifies GeminiProvider handles 401, 404, and malformed SSE data cleanly."""
        provider = GeminiProvider()
        provider.api_key = "test_gemini_key"

        # Test 401
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        mock_ctx_401 = MagicMock()
        mock_ctx_401.__aenter__ = AsyncMock(return_value=mock_resp_401)
        mock_ctx_401.__aexit__ = AsyncMock(return_value=None)
        mock_client_401 = MagicMock()
        mock_client_401.stream = MagicMock(return_value=mock_ctx_401)
        mock_client_401.__aenter__ = AsyncMock(return_value=mock_client_401)
        mock_client_401.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client_401):
            with self.assertRaises(RuntimeError) as cm:
                async for _ in provider.stream([{"role": "user", "content": "hi"}]):
                    pass
            self.assertIn("HTTP 401", str(cm.exception))

        # Test malformed SSE line (should be skipped without crashing)
        sse_lines = [
            'data: NOT_VALID_JSON',
            'data: {"candidates": [{"content": {"parts": [{"text": "Recovered"}]}}]}'
        ]
        async def fake_aiter():
            for line in sse_lines:
                yield line

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.aiter_lines = fake_aiter
        mock_ctx_ok = MagicMock()
        mock_ctx_ok.__aenter__ = AsyncMock(return_value=mock_resp_ok)
        mock_ctx_ok.__aexit__ = AsyncMock(return_value=None)
        mock_client_ok = MagicMock()
        mock_client_ok.stream = MagicMock(return_value=mock_ctx_ok)
        mock_client_ok.__aenter__ = AsyncMock(return_value=mock_client_ok)
        mock_client_ok.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client_ok):
            received = []
            async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
                received.append(chunk)
            self.assertEqual(received, ["Recovered"])

    # -------------------------------------------------------------------------
    # 3. AI Router Streaming Filter & Reasoning Suppression
    # -------------------------------------------------------------------------
    async def test_06_ai_router_filters_reasoning_incrementally(self):
        """Verifies AIRouter suppresses <think> reasoning while streaming user-facing tokens immediately."""
        router = AIRouter()

        async def stream_with_think():
            chunks = [
                "<think>",
                "Internal reasoning step 1\n",
                "Internal reasoning step 2",
                "</think>",
                "Here is ",
                "the real answer."
            ]
            for c in chunks:
                yield c

        filtered = []
        async for chunk in router._stream_with_filter(stream_with_think()):
            filtered.append(chunk)

        self.assertEqual(filtered, ["Here is ", "the real answer."])
        self.assertEqual("".join(filtered), "Here is the real answer.")

    async def test_07_ai_router_split_tag_boundaries(self):
        """Verifies AIRouter handles tags split across multiple chunks without leaking or eating text."""
        router = AIRouter()

        async def stream_split_tags():
            # <think> split as "<th" and "ink>"
            # </think> split as "</th" and "ink>"
            chunks = [
                "Intro <th",
                "ink>hidden thought</th",
                "ink>Outro"
            ]
            for c in chunks:
                yield c

        filtered = []
        async for chunk in router._stream_with_filter(stream_split_tags()):
            filtered.append(chunk)

        self.assertEqual("".join(filtered), "Intro Outro")

    async def test_08_ai_router_groq_failover_to_gemini_when_no_tokens_yielded(self):
        """Verifies clean failover from Groq to Gemini if Groq fails before emitting any tokens."""
        router = AIRouter()
        router.groq_provider.api_key = "test_groq_key"
        router.gemini_provider.api_key = "test_gemini_key"

        async def failing_groq(messages):
            raise RuntimeError("Groq API rate limit (0 tokens emitted)")
            if False:
                yield "never"

        async def working_gemini(messages):
            yield "Fallback "
            yield "Gemini "
            yield "Response"

        router.groq_provider.stream = failing_groq
        router.gemini_provider.stream = working_gemini

        received = []
        async for chunk in router.stream_response([{"role": "user", "content": "hi"}]):
            received.append(chunk)

        self.assertEqual("".join(received), "Fallback Gemini Response")

    async def test_09_ai_router_no_failover_if_groq_already_yielded(self):
        """
        Verifies that if Groq fails AFTER yielding tokens, AIRouter terminates
        without calling Gemini, preventing duplicated / stitched responses.
        """
        router = AIRouter()
        router.groq_provider.api_key = "test_groq_key"
        router.gemini_provider.api_key = "test_gemini_key"

        async def partially_working_groq(messages):
            yield "Hello from Groq"
            raise RuntimeError("Groq socket died mid-stream")

        gemini_called = False
        async def working_gemini(messages):
            nonlocal gemini_called
            gemini_called = True
            yield "Should NOT be called"

        router.groq_provider.stream = partially_working_groq
        router.gemini_provider.stream = working_gemini

        received = []
        async for chunk in router.stream_response([{"role": "user", "content": "hi"}]):
            received.append(chunk)

        self.assertEqual("".join(received), "Hello from Groq")
        self.assertFalse(gemini_called, "Gemini was invoked after Groq already emitted tokens!")

    async def test_10_ai_router_all_providers_fail_emits_fallback(self):
        """Verifies safe error message is yielded when all configured providers fail."""
        router = AIRouter()
        router.groq_provider.api_key = "test_groq_key"
        router.gemini_provider.api_key = "test_gemini_key"

        async def failing_stream(messages):
            raise RuntimeError("Provider down")
            if False:
                yield "never"

        router.groq_provider.stream = failing_stream
        router.gemini_provider.stream = failing_stream

        received = []
        async for chunk in router.stream_response([{"role": "user", "content": "hi"}]):
            received.append(chunk)

        full_resp = "".join(received)
        self.assertIn("ByteX AI is currently unavailable", full_resp)

    # -------------------------------------------------------------------------
    # 4. End-to-End Orchestrator (ByteXCore) Streaming Events
    # -------------------------------------------------------------------------
    async def test_11_assistant_process_user_message_streaming_events(self):
        """
        Verifies that ByteXCore.process_user_message emits individual ASSISTANT_DELTA
        events for each incremental chunk, followed by a single ASSISTANT_COMPLETE.
        """
        core = ByteXCore()
        core.clear_history()

        streamed_chunks = ["ByteX ", "incremental ", "token ", "streaming ", "verified!"]

        async def mock_stream_response(history, memory_context=""):
            for c in streamed_chunks:
                yield c

        with patch("core.assistant.ai_router.stream_response", side_effect=mock_stream_response):
            events = []
            async for ev in core.process_user_message("Explain quantum computing in one sentence."):
                events.append(ev)

            # Check event types sequence
            types = [e.type for e in events]
            self.assertIn("STATE_CHANGE", types)
            self.assertIn("ASSISTANT_DELTA", types)
            self.assertIn("ASSISTANT_COMPLETE", types)

            # Verify delta events matched streamed chunks
            delta_events = [e for e in events if e.type == "ASSISTANT_DELTA"]
            self.assertEqual(len(delta_events), len(streamed_chunks))
            deltas_received = [e.content for e in delta_events]
            self.assertEqual(deltas_received, streamed_chunks)

            # Verify complete event has full assembled string
            complete_events = [e for e in events if e.type == "ASSISTANT_COMPLETE"]
            self.assertEqual(len(complete_events), 1)
            self.assertEqual(complete_events[0].message, "".join(streamed_chunks))

    # -------------------------------------------------------------------------
    # 5. Backward Compatibility (Non-Streaming generate)
    # -------------------------------------------------------------------------
    async def test_12_non_streaming_generate_still_works(self):
        """Verifies provider.generate() still produces full responses via streaming accumulation."""
        groq = GroqProvider()
        groq.api_key = "key"

        async def fake_stream(messages, **kwargs):
            for word in ["Complete ", "synchronous ", "response"]:
                yield word

        groq.stream = fake_stream
        res = await groq.generate([{"role": "user", "content": "hi"}])
        self.assertEqual(res, "Complete synchronous response")

    # -------------------------------------------------------------------------
    # 6. WebSocket Security & Protocol Leakage Guard
    # -------------------------------------------------------------------------
    async def test_13_websocket_sanitizes_delta_leakage(self):
        """Verifies WebSocket ConnectionManager blocks ASSISTANT_DELTA containing internal protocol tags."""
        mgr = ConnectionManager()
        ws = MagicMock()
        ws.send_text = AsyncMock()

        # Normal delta passes through
        normal_delta = create_delta_event("Normal token")
        await mgr.send_event(ws, normal_delta)
        self.assertEqual(ws.send_text.call_count, 1)

        # Delta with <think> tag must be blocked
        leaky_delta = create_delta_event("<think>internal secret</think>")
        await mgr.send_event(ws, leaky_delta)
        # Call count should not increase
        self.assertEqual(ws.send_text.call_count, 1)

        # Delta with <tool_call> must be blocked
        tool_delta = create_delta_event("<tool_call>")
        await mgr.send_event(ws, tool_delta)
        self.assertEqual(ws.send_text.call_count, 1)


if __name__ == "__main__":
    unittest.main()

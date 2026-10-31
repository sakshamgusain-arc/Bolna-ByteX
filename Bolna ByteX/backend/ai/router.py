import logging
import re
from typing import AsyncGenerator, List, Dict, Any
from ai.providers.groq_provider import GroqProvider
from ai.providers.gemini_provider import GeminiProvider
from ai.prompts.system import get_system_prompt
from config.settings import settings

logger = logging.getLogger("bytex.ai_router")

class AIRouter:
    """Intelligent Router with automatic failover (Groq -> Gemini -> Friendly Error) and genuine token streaming."""
    
    def __init__(self):
        self.groq_provider = GroqProvider()
        self.gemini_provider = GeminiProvider()

    def _prepare_messages(self, user_history: List[Dict[str, str]], memory_context: str = "") -> List[Dict[str, str]]:
        system_content = get_system_prompt()
        if memory_context:
            system_content += f"\n{memory_context}"
            
        messages = [{"role": "system", "content": system_content}]
        messages.extend(user_history[-10:])
        return messages

    async def _stream_with_filter(self, stream_gen: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        """
        Incrementally streams tokens while suppressing internal reasoning tags (<think>...</think>, <thought>...</thought>).
        Emits user-facing tokens immediately as they arrive without buffering completed responses.
        """
        in_think = False
        think_buffer = []
        pending = ""
        yielded_any = False

        OPEN_TAGS = ["<think>", "<thought>"]
        CLOSE_TAGS = ["</think>", "</thought>"]

        async for chunk in stream_gen:
            if not chunk:
                continue

            text = pending + chunk
            pending = ""

            while text:
                if not in_think:
                    open_pos = -1
                    matched_open = None
                    for ot in OPEN_TAGS:
                        pos = text.lower().find(ot)
                        if pos != -1 and (open_pos == -1 or pos < open_pos):
                            open_pos = pos
                            matched_open = ot

                    if open_pos != -1:
                        before = text[:open_pos]
                        if before:
                            yielded_any = True
                            yield before
                        in_think = True
                        text = text[open_pos + len(matched_open):]
                    else:
                        partial_match = False
                        for ot in OPEN_TAGS:
                            for l in range(min(len(text), len(ot) - 1), 0, -1):
                                if ot.startswith(text[-l:].lower()):
                                    pending = text[-l:]
                                    to_yield = text[:-l]
                                    if to_yield:
                                        yielded_any = True
                                        yield to_yield
                                    text = ""
                                    partial_match = True
                                    break
                            if partial_match:
                                break
                        if not partial_match:
                            yielded_any = True
                            yield text
                            text = ""
                else:
                    close_pos = -1
                    matched_close = None
                    for ct in CLOSE_TAGS:
                        pos = text.lower().find(ct)
                        if pos != -1 and (close_pos == -1 or pos < close_pos):
                            close_pos = pos
                            matched_close = ct

                    if close_pos != -1:
                        think_buffer.append(text[:close_pos])
                        in_think = False
                        text = text[close_pos + len(matched_close):]
                        if not yielded_any:
                            text = text.lstrip("\r\n")
                    else:
                        partial_match = False
                        for ct in CLOSE_TAGS:
                            for l in range(min(len(text), len(ct) - 1), 0, -1):
                                if ct.startswith(text[-l:].lower()):
                                    pending = text[-l:]
                                    think_buffer.append(text[:-l])
                                    text = ""
                                    partial_match = True
                                    break
                            if partial_match:
                                break
                        if not partial_match:
                            think_buffer.append(text)
                            text = ""

        if pending:
            if not in_think:
                yielded_any = True
                yield pending
            else:
                think_buffer.append(pending)

        # If stream finished while still in think block and nothing was yielded to user:
        if not yielded_any and think_buffer:
            full_think = "".join(think_buffer).strip()
            lines = [
                l.strip() for l in full_think.split("\n")
                if l.strip()
                and not l.strip().lower().startswith("thinking")
                and not l.strip().startswith("1.")
                and not l.strip().startswith("2.")
                and not l.strip().startswith("*self")
            ]
            if lines:
                candidate = lines[-1]
                candidate = re.sub(r'\(Self-correction:.*?\)', '', candidate, flags=re.DOTALL).strip()
                if candidate:
                    yield candidate

    async def stream_response(self, history: List[Dict[str, str]], memory_context: str = "") -> AsyncGenerator[str, None]:
        """Streams AI responses with relevant memory context injection and failover."""
        messages = self._prepare_messages(history, memory_context)

        # 1. Primary Provider: Groq
        if settings.AI_PRIMARY_PROVIDER == "groq" and self.groq_provider.api_key:
            has_yielded = False
            try:
                async for chunk in self._stream_with_filter(self.groq_provider.stream(messages)):
                    has_yielded = True
                    yield chunk
                if has_yielded:
                    return
            except Exception as e:
                logger.warning(f"[AI Router] Groq stream failed (yielded={has_yielded}): {e}")
                if has_yielded:
                    # Once tokens were emitted to caller, do not fallback to Gemini to prevent duplicate output
                    return

        # 2. Fallback Provider: Gemini
        if self.gemini_provider.api_key:
            has_yielded = False
            try:
                async for chunk in self._stream_with_filter(self.gemini_provider.stream(messages)):
                    has_yielded = True
                    yield chunk
                if has_yielded:
                    return
            except Exception as e:
                logger.error(f"[AI Router] Gemini stream failed (yielded={has_yielded}): {e}")
                if has_yielded:
                    return

        # 3. Graceful Error Event Output
        logger.error("[AI Router] All providers failed. Emitting safe fallback message.")
        yield "ByteX AI is currently unavailable. Check the backend provider configuration."

ai_router = AIRouter()

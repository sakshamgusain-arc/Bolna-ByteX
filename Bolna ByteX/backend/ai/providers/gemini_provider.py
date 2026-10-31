import json
import logging
import httpx
from typing import AsyncGenerator, List, Dict, Any
from ai.providers.base import AIProvider
from config.settings import settings

logger = logging.getLogger("bytex.gemini_provider")

class GeminiProvider(AIProvider):
    """Native Async Gemini Fallback Provider implementation with genuine SSE streaming."""
    
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL

    async def health_check(self) -> bool:
        return bool(self.api_key)

    async def generate(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        chunks = []
        async for chunk in self.stream(messages, **kwargs):
            chunks.append(chunk)
        return "".join(chunks)

    async def stream(self, messages: List[Dict[str, str]], **kwargs: Any) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        # Build message history prompt
        formatted_prompt = []
        for msg in messages:
            role = "Assistant" if msg["role"] == "assistant" else "User"
            if msg["role"] == "system":
                formatted_prompt.append(f"System: {msg['content']}")
            else:
                formatted_prompt.append(f"{role}: {msg['content']}")
        
        prompt_text = "\n".join(formatted_prompt)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?alt=sse&key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}]
        }

        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        try:
                            chunk_data = json.loads(data_str)
                            candidates = chunk_data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    text_val = part.get("text", "")
                                    if text_val:
                                        yield text_val
                        except Exception as ex:
                            logger.debug(f"[GeminiProvider] SSE JSON parse warning: {ex}")
                            continue
                elif response.status_code == 401:
                    logger.error("[GeminiProvider] Authentication failed (HTTP 401): Invalid or expired GEMINI_API_KEY.")
                    raise RuntimeError("Gemini REST error HTTP 401: Invalid or expired GEMINI_API_KEY.")
                elif response.status_code == 404:
                    logger.error(f"[GeminiProvider] Model '{self.model}' not found (HTTP 404).")
                    raise RuntimeError(f"Gemini model '{self.model}' not found (HTTP 404).")
                else:
                    err_body = await response.aread()
                    err_text = err_body.decode("utf-8", errors="ignore")[:200]
                    logger.error(f"[GeminiProvider] HTTP {response.status_code}: {err_text}")
                    raise RuntimeError(f"Gemini REST error HTTP {response.status_code}: {err_text}")

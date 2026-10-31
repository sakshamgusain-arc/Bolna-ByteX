import sys
import os
import asyncio
import time

sys.path.insert(0, os.path.abspath("backend"))
from config.settings import settings
from ai.providers.groq_provider import GroqProvider
from ai.providers.gemini_provider import GeminiProvider
from core.assistant import ByteXCore

async def test_live():
    groq_has_key = bool(settings.GROQ_API_KEY and len(settings.GROQ_API_KEY.strip()) > 5)
    gemini_has_key = bool(settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY.strip()) > 5)

    print(f"GROQ_CONFIGURED: {groq_has_key}")
    print(f"GEMINI_CONFIGURED: {gemini_has_key}")

    # 1. Test Groq Live Streaming
    if groq_has_key:
        print("\n--- TESTING LIVE GROQ STREAMING ---")
        groq = GroqProvider()
        chunks = []
        t0 = time.time()
        t_first = None
        try:
            async for chunk in groq.stream([{"role": "user", "content": "Respond with only: Hello ByteX"}]):
                if t_first is None:
                    t_first = time.time()
                chunks.append(chunk)
            t_total = time.time()
            first_ms = (t_first - t0) * 1000 if t_first else None
            total_ms = (t_total - t0) * 1000
            assembled = "".join(chunks).strip()
            print("GROQ_STATUS: SUCCESS")
            print(f"GROQ_CHUNKS_COUNT: {len(chunks)}")
            print(f"GROQ_FIRST_TOKEN_LATENCY: {first_ms:.1f}ms" if first_ms else "GROQ_FIRST_TOKEN_LATENCY: None")
            print(f"GROQ_TOTAL_DURATION: {total_ms:.1f}ms")
            print(f"GROQ_ASSEMBLED_OUTPUT: {assembled}")
        except Exception as e:
            print(f"GROQ_STATUS: FAILED ({type(e).__name__}: {str(e)[:150]})")
    else:
        print("\nGROQ: NOT CONFIGURED")

    # 2. Test Gemini Live Streaming
    if gemini_has_key:
        print("\n--- TESTING LIVE GEMINI SSE STREAMING ---")
        gemini = GeminiProvider()
        chunks = []
        t0 = time.time()
        t_first = None
        try:
            async for chunk in gemini.stream([{"role": "user", "content": "Respond with only: Hello ByteX"}]):
                if t_first is None:
                    t_first = time.time()
                chunks.append(chunk)
            t_total = time.time()
            first_ms = (t_first - t0) * 1000 if t_first else None
            total_ms = (t_total - t0) * 1000
            assembled = "".join(chunks).strip()
            print("GEMINI_STATUS: SUCCESS")
            print(f"GEMINI_CHUNKS_COUNT: {len(chunks)}")
            print(f"GEMINI_FIRST_TOKEN_LATENCY: {first_ms:.1f}ms" if first_ms else "GEMINI_FIRST_TOKEN_LATENCY: None")
            print(f"GEMINI_TOTAL_DURATION: {total_ms:.1f}ms")
            print(f"GEMINI_ASSEMBLED_OUTPUT: {assembled}")
        except Exception as e:
            print(f"GEMINI_STATUS: FAILED ({type(e).__name__}: {str(e)[:150]})")
    else:
        print("\nGEMINI: NOT CONFIGURED")

    # 3. Test End-to-End Core Streaming
    print("\n--- TESTING LIVE END-TO-END ASSISTANT STREAMING ---")
    core = ByteXCore()
    core.clear_history()
    events = []
    t0 = time.time()
    t_first_delta = None
    try:
        async for ev in core.process_user_message("Respond with only: Hello ByteX Core"):
            if ev.type == "ASSISTANT_DELTA" and t_first_delta is None:
                t_first_delta = time.time()
            events.append(ev)
        t_total = time.time()
        delta_events = [e for e in events if e.type == "ASSISTANT_DELTA"]
        complete_events = [e for e in events if e.type == "ASSISTANT_COMPLETE"]
        first_delta_ms = (t_first_delta - t0) * 1000 if t_first_delta else None
        total_e2e_ms = (t_total - t0) * 1000
        print("CORE_STATUS: SUCCESS")
        print(f"TOTAL_EVENTS: {len(events)}")
        print(f"DELTA_EVENTS_COUNT: {len(delta_events)}")
        print(f"FIRST_DELTA_LATENCY: {first_delta_ms:.1f}ms" if first_delta_ms else "FIRST_DELTA_LATENCY: None")
        print(f"TOTAL_E2E_DURATION: {total_e2e_ms:.1f}ms")
        if complete_events:
            print(f"FINAL_MESSAGE: {complete_events[0].message}")
    except Exception as e:
        print(f"CORE_STATUS: FAILED ({type(e).__name__}: {str(e)[:150]})")

if __name__ == "__main__":
    asyncio.run(test_live())

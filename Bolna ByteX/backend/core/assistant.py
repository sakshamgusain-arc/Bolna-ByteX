import asyncio
import re
import traceback
from typing import AsyncGenerator, List, Dict
from ai.router import ai_router
from core.command_router import CommandRouter
from memory.service import memory_service
from core.events import (
    create_state_event,
    create_delta_event,
    create_complete_event,
    create_error_event,
)
from models.schemas import WSEvent
from config.settings import settings

from core.response_sanitizer import ResponseSanitizer

def extract_clean_ai_response(raw_text: str) -> str:
    """
    Extracts the clean, user-facing AI response from raw model outputs using ResponseSanitizer.
    Guarantees no internal reasoning tags or agent protocol are ever returned.
    """
    return ResponseSanitizer.sanitize(raw_text)

class ByteXCore:
    """Central Orchestration Engine for ByteX AI."""
    
    def __init__(self):
        self.assistant_name = "ByteX Core"
        self.version = "0.1.0"
        self.current_state = "idle"
        self.history: List[Dict[str, str]] = []
        
        groq_status = "configured" if bool(settings.GROQ_API_KEY) else "not configured"
        gemini_status = "configured" if bool(settings.GEMINI_API_KEY) else "not configured"
        print(f"[ByteX Core] GROQ_API_KEY: {groq_status}")
        print(f"[ByteX Core] GEMINI_API_KEY: {gemini_status}")

    def clear_history(self):
        self.history = []

    async def process_user_message(self, message: str) -> AsyncGenerator[WSEvent, None]:
        """Processes user message via Skill Registry, Memory Engine & AI Router with real-time events."""
        print(f"[ByteX Core] Received: '{message}'")
        try:
            # 1. State -> THINKING
            self.current_state = "thinking"
            yield create_state_event("thinking")

            # 2. Check for explicit PC automation skills or memory commands
            is_handled, direct_response, target_state, data = await CommandRouter.route_command(message, self.history)
            
            if is_handled:
                # Signal EXECUTING state if skill automation triggered
                self.current_state = "executing"
                yield create_state_event("executing")
                await asyncio.sleep(0.3)

                self.current_state = target_state
                yield create_state_event(target_state)
                clean_direct = ResponseSanitizer.sanitize(direct_response) if direct_response else ""
                yield create_complete_event(clean_direct, state=target_state, data=data)
                
                if target_state != "idle":
                    await asyncio.sleep(0.1)
                    self.current_state = "idle"
                    yield create_state_event("idle")
                return

            # 3. Retrieve relevant user memory context
            memory_context = memory_service.get_context_for_prompt(message)
            if memory_context:
                print(f"[ByteX Core] Injected relevant memory context into system prompt.")

            # 4. Append to session context
            self.history.append({"role": "user", "content": message})

            # 5. Call AI Router
            print("[ByteX Core] Calling AI Router with memory context...")
            self.current_state = "speaking"
            yield create_state_event("speaking")

            max_tool_iterations = 4
            iteration = 0
            final_response = ""

            while iteration < max_tool_iterations:
                iteration += 1
                full_response_chunks = []
                is_internal_protocol_stream = False
                
                async for chunk in ai_router.stream_response(self.history, memory_context=memory_context):
                    full_response_chunks.append(chunk)
                    accumulated = "".join(full_response_chunks).lstrip()
                    
                    # Stop streaming if internal agent protocol (tool call, thinking, JSON block) is detected
                    if not is_internal_protocol_stream:
                        if (
                            accumulated.startswith(("{", "<think>", "<tool>", "```json"))
                            or (accumulated.startswith("```") and not accumulated.startswith(("```python", "```cpp", "```c", "```html", "```css", "```js", "```ts", "```bash", "```sh", "```sql")))
                            or "<tool_call>" in accumulated
                            or "<tool>" in accumulated
                            or "<think>" in accumulated
                        ):
                            is_internal_protocol_stream = True
                        else:
                            yield create_delta_event(chunk)

                raw_response = "".join(full_response_chunks)

                # Check if LLM output was an internal tool call to execute
                tool_call = ResponseSanitizer.extract_tool_call(raw_response)
                if tool_call:
                    tool_name, tool_args = tool_call
                    print(f"[ByteX Core] Tool Call #{iteration} detected: '{tool_name}' with args {tool_args}")
                    
                    self.current_state = "executing"
                    yield create_state_event("executing")

                    from skills.registry import skill_registry
                    tool_res = await skill_registry.execute_tool(tool_name, tool_args)
                    
                    self.current_state = "speaking"
                    yield create_state_event("speaking")

                    tool_feedback = tool_res.message
                    if tool_res.error and tool_res.error not in tool_feedback:
                        tool_feedback += f"\nError: {tool_res.error}"

                    # Feed the tool execution and result back into model conversation history
                    self.history.append({"role": "assistant", "content": raw_response})
                    self.history.append({
                        "role": "user",
                        "content": f"[Tool Result for '{tool_name}']:\n{tool_feedback}"
                    })
                    # Loop back to generate response or next tool call
                    continue
                else:
                    # Model produced a final textual response
                    final_response = ResponseSanitizer.sanitize(raw_response)
                    break

            if not final_response:
                final_response = "Operation completed."

            print("[ByteX Core] AI response completed")

            # 6. Append assistant response to session context
            self.history.append({"role": "assistant", "content": final_response})

            # 7. Emit ASSISTANT_COMPLETE (guaranteed sanitized)
            yield create_complete_event(final_response)

            # 8. Return to IDLE
            await asyncio.sleep(0.1)
            self.current_state = "idle"
            yield create_state_event("idle")

        except Exception as e:
            print(f"[ByteX Core Error]: {e}")
            traceback.print_exc()
            self.current_state = "error"
            yield create_error_event("ByteX AI is currently unavailable. Check backend configuration.")
            await asyncio.sleep(1.0)
            self.current_state = "idle"
            yield create_state_event("idle")

bytex_core = ByteXCore()

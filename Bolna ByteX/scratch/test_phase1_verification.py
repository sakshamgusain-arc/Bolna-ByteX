import asyncio
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from core.command_router import CommandRouter
from agent.planner import ByteXPlanner
from core.session import session_manager
from skills.media import media_session_manager

async def run_tests():
    print("=" * 60)
    print("RUNNING PHASE 1 VERIFICATION TESTS")
    print("=" * 60)

    # -------------------------------------------------------------
    # TEST 1: Ordinary Notepad Text Entry vs Code Generation in Planner
    # -------------------------------------------------------------
    print("\n--- TEST 1: Planner Goal Decomposition ---")
    
    # 1A: "Open Notepad and write I am Yash"
    p1 = ByteXPlanner.generate_plan("Open Notepad and write I am Yash")
    assert p1 is not None, "Failed: p1 is None"
    assert len(p1.steps) == 2, f"Failed: expected 2 steps, got {len(p1.steps)}"
    assert p1.steps[0].suggested_skill == "open_application", f"Failed step 0 skill: {p1.steps[0].suggested_skill}"
    assert p1.steps[0].arguments.get("application") == "Notepad"
    assert p1.steps[1].suggested_skill == "screen_vision", f"Failed step 1 skill: {p1.steps[1].suggested_skill}"
    assert p1.steps[1].arguments.get("action") == "visual_type"
    assert p1.steps[1].arguments.get("text") == "I am Yash", f"Failed text: {p1.steps[1].arguments.get('text')}"
    print("[PASS] 1A: 'Open Notepad and write I am Yash' generates open_app + screen_vision(text='I am Yash')")

    # 1B: "Write I am Yash in Notepad"
    p2 = ByteXPlanner.generate_plan("Write I am Yash in Notepad")
    assert p2 is not None, "Failed: p2 is None"
    assert len(p2.steps) == 2, f"Failed: expected 2 steps, got {len(p2.steps)}"
    assert p2.steps[0].suggested_skill == "open_application"
    assert p2.steps[1].suggested_skill == "screen_vision"
    assert p2.steps[1].arguments.get("text") == "I am Yash"
    print("[PASS] 1B: 'Write I am Yash in Notepad' generates open_app + screen_vision(text='I am Yash')")

    # 1C: "Write a Python program that prints Hello World"
    cls_code1 = await CommandRouter.classify_request("Write a Python program that prints Hello World")
    assert cls_code1.get("skill") == "coding_workspace", f"Failed: {cls_code1}"
    assert cls_code1.get("arguments", {}).get("action") == "generate_code"
    print("[PASS] 1C: 'Write a Python program that prints Hello World' routes to coding_workspace(generate_code)")

    # 1D: "Write code in C++ to reverse an array"
    cls_code2 = await CommandRouter.classify_request("Write code in C++ to reverse an array")
    assert cls_code2.get("skill") == "coding_workspace", f"Failed: {cls_code2}"
    assert cls_code2.get("arguments", {}).get("action") == "generate_code"
    print("[PASS] 1D: 'Write code in C++ to reverse an array' routes to coding_workspace(generate_code)")

    # -------------------------------------------------------------
    # TEST 2: Stop Listening vs Application Closing
    # -------------------------------------------------------------
    print("\n--- TEST 2: Stop Listening Routing ---")
    
    # Ensure session is active
    session_manager.start_or_renew_session(target="Notepad", action="open_application")
    assert session_manager.is_session_active(), "Session should be active"

    is_h, resp, st, data = await CommandRouter.route_command("Stop listening", [])
    assert is_h is True
    assert st == "idle"
    assert data.get("action") == "standby"
    assert data.get("keep_listening") is False
    assert not session_manager.is_session_active(), "Session should be ended"
    print(f"[PASS] 2A: 'Stop listening' returned standby route (not close_application): '{resp}'")

    # Verify "listening" is not closed as an app
    parsed_intent = await CommandRouter.parse_skill_intent("stop listening")
    assert parsed_intent is None, f"Expected None, got {parsed_intent}"
    print("[PASS] 2B: 'stop listening' does NOT parse as close_application('listening')")

    parsed_talking = await CommandRouter.parse_skill_intent("stop talking")
    assert parsed_talking is None, f"Expected None, got {parsed_talking}"
    print("[PASS] 2C: 'stop talking' does NOT parse as close_application('talking')")

    # -------------------------------------------------------------
    # TEST 3: Stop Talking vs Stop
    # -------------------------------------------------------------
    print("\n--- TEST 3: Stop Talking vs Stop ---")
    
    is_h, resp, st, data = await CommandRouter.route_command("Stop talking", [])
    assert is_h is True
    assert st == "idle"
    assert resp == "", "Stop talking should return empty response to avoid speaking again"
    assert data.get("action") == "stop_talking"
    assert data.get("keep_listening") is True
    print("[PASS] 3A: 'Stop talking' returns empty speech + keep_listening=True")

    is_h, resp, st, data = await CommandRouter.route_command("Stop", [])
    assert is_h is True
    assert st == "idle"
    assert resp == "Stopped."
    assert data.get("action") == "stop"
    assert data.get("keep_listening") is True
    print("[PASS] 3B: 'Stop' returns 'Stopped.' + keep_listening=True")

    # -------------------------------------------------------------
    # TEST 4: Pause and Continue
    # -------------------------------------------------------------
    print("\n--- TEST 4: Pause and Continue Separation ---")
    
    # 4A: Pause with no active task or media
    session_manager.end_session()
    is_h, resp, st, data = await CommandRouter.route_command("Pause", [])
    assert is_h is True
    assert st == "idle"
    assert data.get("action") == "pause"
    assert data.get("task_paused") is False
    print(f"[PASS] 4A: 'Pause' (no task): '{resp}'")

    # 4B: Pause with active task session
    session_manager.start_or_renew_session(target="Notepad", action="open_application")
    is_h, resp, st, data = await CommandRouter.route_command("Pause", [])
    assert is_h is True
    assert st == "idle"
    assert data.get("action") == "pause"
    assert data.get("task_paused") is True
    assert session_manager.is_paused() is True, "Session should be marked paused"
    print(f"[PASS] 4B: 'Pause' (with task): '{resp}'")

    # 4C: Continue with paused session
    is_h, resp, st, data = await CommandRouter.route_command("Continue", [])
    assert is_h is True, "Continue should be handled, not fall through to LLM"
    assert st == "speaking"
    assert data.get("action") == "resume"
    assert data.get("resumed") is True
    assert session_manager.is_paused() is False, "Session should be unpaused"
    print(f"[PASS] 4C: 'Continue' resumes preserved context: '{resp}'")

    # 4D: Continue when nothing was paused
    session_manager.end_session()
    is_h, resp, st, data = await CommandRouter.route_command("Continue", [])
    assert is_h is True, "Continue should be handled even if nothing paused"
    assert st == "idle"
    assert data.get("resumed") is False
    print(f"[PASS] 4D: 'Continue' (nothing paused): '{resp}'")

    print("\n" + "=" * 60)
    print("ALL PHASE 1 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())

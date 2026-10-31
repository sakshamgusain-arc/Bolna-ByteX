import asyncio
import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from unittest.mock import patch, AsyncMock
from agent.pipeline import agent_pipeline
from skills.base import ToolResult

async def run_pipeline_test():
    test_commands = [
        ("Open Notepad and write Hello I am Negasaurus.", "Hello I am Negasaurus."),
        ("Open Notepad and write. Hello I am Negasaurus.", "Hello I am Negasaurus."),
        ("Open Notepad and type Hello I am Negasaurus.", "Hello I am Negasaurus."),
        ("Write Hello I am Negasaurus in Notepad.", "Hello I am Negasaurus")
    ]
    
    for cmd, expected_text in test_commands:
        print("\n" + "="*60)
        print(f"RUNNING PIPELINE FOR: '{cmd}'")
        print("="*60)
        mock_type_res = {
            "success": True,
            "verified": True,
            "text": expected_text,
            "target_field": "Notepad",
            "diff_metric": 0.05,
            "window": "Notepad",
            "message": f"Typed '{expected_text}' into Notepad in Notepad."
        }
        with patch("services.visual_verifier.visual_verifier.execute_verified_type", new=AsyncMock(return_value=mock_type_res)):
            with patch("skills.apps.OpenApplicationSkill.execute", new=AsyncMock(return_value=ToolResult(success=True, verified=True, tool="open_application", action="open", message="Notepad opened successfully.", data={"application": "Notepad", "status": "opened"}))):
                success, msg, state, data = await agent_pipeline.run_pipeline(cmd)
                print(f"Pipeline Result:\n  Success: {success}\n  Message: {msg}\n  State: {state}")
                assert success, f"Pipeline failed for '{cmd}': {msg}"
                assert "opened Notepad" in msg or "Notepad opened" in msg or "opened the application" in msg
                assert f"typed '{expected_text}'" in msg, f"Expected typed '{expected_text}' in msg, got: {msg}"
        print(f"PASSED: '{cmd}'")
    
    print("\nALL 4 USER-SPECIFIED PIPELINE RUNS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_pipeline_test())

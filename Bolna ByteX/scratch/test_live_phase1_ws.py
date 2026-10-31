import asyncio
import json
import websockets

async def test_live_phase1():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as ws:
        init_raw = await ws.recv()
        print("Initial WS event:", init_raw)

        async def send_cmd(cmd_text):
            print(f"\n--- SENDING: {cmd_text} ---")
            await ws.send(json.dumps({"message": cmd_text}))
            events = []
            while True:
                raw = await ws.recv()
                evt = json.loads(raw)
                evt_type = evt.get("type")
                events.append(evt)
                if evt_type == "ASSISTANT_COMPLETE":
                    print(f"[ASSISTANT COMPLETE]: {evt.get('message')}")
                    break
            return events

        # Test 1: Stop listening
        evts = await send_cmd("Stop listening")
        assert any("standby" in str(e.get("message", "")).lower() for e in evts), "Stop listening failed!"

        # Test 2: Pause
        evts = await send_cmd("Pause")
        assert any("pause" in str(e.get("message", "")).lower() for e in evts), "Pause failed!"

        # Test 3: Continue
        evts = await send_cmd("Continue")
        assert any("resum" in str(e.get("message", "")).lower() or "nothing" in str(e.get("message", "")).lower() for e in evts), "Continue failed!"

        # Test 4: Live Notepad text entry
        evts = await send_cmd("Open Notepad and write. Hello I am Negasaurus.")
        last_msg = next((e.get("message") for e in reversed(evts) if e.get("type") == "ASSISTANT_COMPLETE"), "")
        print(f"Final assistant message for Notepad typing: {last_msg}")
        assert "could not be found" not in last_msg, f"Regression detected: {last_msg}"
        assert "typed 'Hello I am Negasaurus.'" in last_msg, f"Unexpected message: {last_msg}"

        print("\nALL LIVE PHASE 1 AND NOTEPAD WEBSOCKET TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_live_phase1())

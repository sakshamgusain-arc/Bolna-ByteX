import os
import sys
import subprocess
import time
import httpx
import asyncio
from pathlib import Path

def start():
    print("=" * 60)
    print("  Starting ByteX AI (Unified Edge Architecture)")
    print("=" * 60)
    
    root_dir = Path(__file__).resolve().parent
    bytex_frontend_dir = root_dir / "ByteX"

    # 1. Start Backend if not already running
    backend_running = False
    try:
        r = httpx.get("http://127.0.0.1:8000/", timeout=1.0)
        if r.status_code == 200:
            backend_running = True
            print("[Backend] FastAPI is already running on http://127.0.0.1:8000")
    except Exception:
        pass

    if not backend_running:
        print("[Backend] Starting FastAPI backend on http://127.0.0.1:8000...")
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "8000"],
            cwd=str(root_dir),
            shell=False
        )
        time.sleep(1.5)

    # 2. Start Frontend if not already running
    frontend_running = False
    try:
        r = httpx.get("http://localhost:5173/", timeout=1.0)
        if r.status_code == 200:
            frontend_running = True
            print("[Frontend] Vite React app is already running on http://localhost:5173")
    except Exception:
        pass

    if not frontend_running:
        print("[Frontend] Starting Vite React app on http://localhost:5173...")
        subprocess.Popen(["npm", "run", "dev"], cwd=str(bytex_frontend_dir), shell=True)
        time.sleep(2.5)

    # 3. Launch or Connect to Single Controlled Microsoft Edge with CDP enabled on port 9222
    cdp_running = False
    try:
        r = httpx.get("http://127.0.0.1:9222/json", timeout=1.0)
        if r.status_code == 200:
            cdp_running = True
            print("[Edge] Active Edge session with CDP is already running on port 9222")
    except Exception:
        pass

    edge_user_data = os.path.join(os.environ.get('LOCALAPPDATA', r'C:\Users\Default\AppData\Local'), r'ByteX_Edge_Profile')
    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge_exe = next((c for c in edge_candidates if os.path.exists(c)), "msedge.exe")

    if not cdp_running:
        print("[Edge] Launching Visible Single Controlled Microsoft Edge (ByteX_Edge_Profile) on port 9222...")
        subprocess.Popen([
            edge_exe,
            "--remote-debugging-port=9222",
            f"--user-data-dir={edge_user_data}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=msEdgeStartupBoost",
            "--new-window",
            "http://localhost:5173"
        ])
        
        # Wait up to 10s for CDP to be ready
        for _ in range(20):
            time.sleep(0.5)
            try:
                r = httpx.get("http://127.0.0.1:9222/json", timeout=1.0)
                if r.status_code == 200:
                    cdp_running = True
                    break
            except Exception:
                pass

    # Ensure http://localhost:5173 is open in this EXACT CDP browser instance
    bytex_target_id = None
    if cdp_running:
        try:
            r = httpx.get("http://127.0.0.1:9222/json", timeout=2.0)
            tabs = r.json()
            bytex_tab = next((t for t in tabs if "5173" in t.get("url", "") or "bytex" in t.get("title", "").lower()), None)
            if not bytex_tab:
                new_tab = httpx.put("http://127.0.0.1:9222/json/new?http://localhost:5173", timeout=2.0).json()
                bytex_target_id = new_tab.get("id")
            else:
                bytex_target_id = bytex_tab.get("id")
            
            if bytex_target_id:
                httpx.get(f"http://127.0.0.1:9222/json/activate/{bytex_target_id}", timeout=2.0)
        except Exception as e:
            print(f"[Edge] ByteX tab setup error: {e}")

    print("\n" + "=" * 60)
    print("  ByteX AI is fully online and ready!")
    print("  UI URL          : http://localhost:5173")
    print("  Backend         : http://localhost:8000")
    print("  CDP Port        : 9222")
    print(f"  ByteX Target ID : {bytex_target_id}")
    print("=" * 60)

if __name__ == "__main__":
    start()

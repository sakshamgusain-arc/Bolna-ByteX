import sys
from pathlib import Path

# Configure stdout and stderr for UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add backend directory to Python import path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from api.routes import router as api_router
from api.websocket import router as ws_router
from monitoring.service import live_system_monitor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runtime Path Diagnostics
    import core.command_router as _cr
    import skills.coding as _cd
    print("=" * 60)
    print(f"[ByteX Runtime Diagnostic] Active Backend Root : {backend_dir}")
    print(f"[ByteX Runtime Diagnostic] command_router.py   : {_cr.__file__}")
    print(f"[ByteX Runtime Diagnostic] coding.py           : {_cd.__file__}")
    print("=" * 60)

    # Startup: Start Live System Monitor
    await live_system_monitor.start()
    
    # Startup: Run enabled Startup Automations (Feature #36.14)
    try:
        from agent.automation import automation_manager
        import asyncio
        asyncio.create_task(automation_manager.run_startup_automations())
    except Exception as e:
        print(f"[Main] Error launching startup automations: {e}")

    yield
    # Shutdown: Cleanly Stop Live System Monitor
    await live_system_monitor.stop()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router, prefix=settings.API_PREFIX)
app.include_router(ws_router)

from api.phone_routes import router as phone_router
app.include_router(phone_router, prefix=settings.API_PREFIX)
app.include_router(phone_router)  # also includes /ws/phone WebSocket route

@app.get("/")
async def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.inference_worker import InferenceWorker
from core.model_adapters import ModelRegistry
from core.robot_store import RobotStore
from routers.control import router as control_router
from routers.stream import router as stream_router

logger = logging.getLogger("pest_robot_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:
    # Startup
    app.state.robot_store = RobotStore(db_url="sqlite:///./robot_store.db")
    app.state.command_queues = {}

    model_root = Path(__file__).parent / "models"
    app.state.model_registry = ModelRegistry(model_root)
    app.state.model_registry.discover()
    models = app.state.model_registry.list_models()
    if not models:
        raise RuntimeError("No detection models were discovered in the models directory")
    # Prefer a .pt (RF-DETR) model as the default if available, otherwise fall back
    default_model_name = next(
        (m["name"] for m in models if m.get("metadata", {}).get("format") == ".pt"),
        None,
    )
    if not default_model_name:
        # Fallback: prefer architectures with 'rfdtr' then keep existing heuristic
        default_model_name = next((m["name"] for m in models if "rfdtr" in m.get("architecture", "").lower()), None)
    if not default_model_name:
        default_model_name = "onnx" if any(m["name"] == "onnx" for m in models) else models[0]["name"]
    app.state.inference_worker = InferenceWorker(app.state.model_registry, app.state.robot_store, default_model_name=default_model_name)
    await app.state.inference_worker.start()

    # Preload the default model in the background so startup stays fast
    async def _preload_default_model() -> None:
        try:
            adapter = app.state.model_registry.get(default_model_name)
            logger.info("Preloading default model %s in background", default_model_name)
            await asyncio.to_thread(adapter.load)
            logger.info("Preloaded default model %s", default_model_name)
        except Exception:
            logger.exception("Failed to preload default model %s", default_model_name)

    app.state.preload_task = asyncio.create_task(_preload_default_model())

    app.state.shutdown_event = asyncio.Event()
    app.state.worker_task = asyncio.create_task(
        app.state.inference_worker.run(app.state.shutdown_event)
    )

    try:
        yield
    finally:
        # Shutdown
        if hasattr(app.state, "shutdown_event"):
            app.state.shutdown_event.set()
        if hasattr(app.state, "preload_task"):
            try:
                app.state.preload_task.cancel()
                await app.state.preload_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error while awaiting preload task during shutdown")
        if hasattr(app.state, "worker_task"):
            await app.state.worker_task


app = FastAPI(title="Pest Detection Robot Server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(control_router)
app.include_router(stream_router)


@app.get("/health")
async def health_check() -> dict:
    model_registry = getattr(app.state, "model_registry", None)
    robot_count = len(app.state.robot_store.get_all_robots()) if hasattr(app.state, "robot_store") else 0
    return {
        "status": "ok",
        "models": model_registry.list_models() if model_registry else [],
        "robot_count": robot_count,
    }

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.inference_worker import InferenceWorker
from core.model_adapters import ModelRegistry
from core.robot_store import RobotStore
from routers.control import router as control_router
from routers.stream import router as stream_router

logger = logging.getLogger("pest_robot_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Pest Detection Robot Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(control_router)
app.include_router(stream_router)


@app.on_event("startup")
async def startup_event() -> None:
    app.state.robot_store = RobotStore(db_url="sqlite:///./robot_store.db")
    app.state.command_queues = {}

    model_root = Path(__file__).parent / "models"
    app.state.model_registry = ModelRegistry(model_root)
    app.state.model_registry.discover()
    models = app.state.model_registry.list_models()
    if not models:
        raise RuntimeError("No detection models were discovered in the models directory")

    default_model_name = "onnx" if any(m["name"] == "onnx" for m in models) else models[0]["name"]
    app.state.inference_worker = InferenceWorker(app.state.model_registry, app.state.robot_store, default_model_name=default_model_name)
    await app.state.inference_worker.start()

    app.state.shutdown_event = asyncio.Event()
    app.state.worker_task = asyncio.create_task(
        app.state.inference_worker.run(app.state.shutdown_event)
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if hasattr(app.state, "shutdown_event"):
        app.state.shutdown_event.set()
    if hasattr(app.state, "worker_task"):
        await app.state.worker_task


@app.get("/health")
async def health_check() -> dict:
    model_registry = getattr(app.state, "model_registry", None)
    robot_count = len(app.state.robot_store.get_all_robots()) if hasattr(app.state, "robot_store") else 0
    return {
        "status": "ok",
        "models": model_registry.list_models() if model_registry else [],
        "robot_count": robot_count,
    }

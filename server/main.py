import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv  # installed with uvicorn[standard]
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(Path(__file__).parent / ".env")

from core.auth import warn_if_auth_disabled
from core.background import run_in_daemon_thread
from core.inference_worker import InferenceWorker
from core.model_adapters import ModelRegistry
from core.robot_store import RobotStore
from core.sightings import SightingStore
from core.viewer_hub import ViewerHub
from routers.control import router as control_router
from routers.history import router as history_router
from routers.stream import router as stream_router

logger = logging.getLogger("pest_robot_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


SIGHTING_FLUSH_SECONDS = 5.0


def create_app(
    model_registry: Optional[ModelRegistry] = None,
    db_url: str = "sqlite:///./robot_store.db",
    data_dir: Optional[Path] = None,
) -> FastAPI:
    """Build the server. Tests pass their own model registry, database and data folder."""
    data_dir = data_dir or Path(__file__).parent / "data"

    @asynccontextmanager
    async def lifespan(app) -> AsyncGenerator[None, None]:
        # Startup
        warn_if_auth_disabled()
        app.state.robot_store = RobotStore(db_url=db_url)
        # A crash or shutdown can leave robots marked online/streaming in the database.
        app.state.robot_store.mark_all_disconnected()
        app.state.command_queues = {}
        # Active robot sockets, so a stale socket closing never marks a reconnected robot offline.
        app.state.control_connections = {}
        app.state.stream_connections = {}
        # Per streaming robot: "server" (server detects) or "monitor" (robot detects).
        app.state.stream_modes = {}
        # Per connected robot: live status from its heartbeats (motors, auto_spray, spraying...).
        app.state.robot_live = {}
        app.state.viewer_hub = ViewerHub()
        app.state.sightings = SightingStore(db_url, snapshot_dir=data_dir / "snapshots")

        if model_registry is None:
            app.state.model_registry = ModelRegistry(Path(__file__).parent / "models")
            app.state.model_registry.discover()
        else:
            app.state.model_registry = model_registry
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
        app.state.inference_worker = InferenceWorker(
            app.state.model_registry,
            app.state.robot_store,
            app.state.viewer_hub,
            default_model_name=default_model_name,
            sightings=app.state.sightings,
        )
        await app.state.inference_worker.start()

        # Preload the default model in the background so startup stays fast
        async def _preload_default_model() -> None:
            try:
                adapter = app.state.model_registry.get(default_model_name)
                logger.info("Preloading default model %s in background", default_model_name)
                # Daemon thread: stopping the server mid-load must not wait for the load.
                await run_in_daemon_thread(adapter.ensure_loaded, name="model-preload")
                logger.info("Preloaded default model %s", default_model_name)
            except Exception:
                logger.exception("Failed to preload default model %s", default_model_name)

        app.state.preload_task = asyncio.create_task(_preload_default_model())

        app.state.shutdown_event = asyncio.Event()

        # Saves active sightings and closes ones whose pest is gone, even when no frames arrive.
        async def _flush_sightings_periodically() -> None:
            while not app.state.shutdown_event.is_set():
                try:
                    await asyncio.wait_for(app.state.shutdown_event.wait(), timeout=SIGHTING_FLUSH_SECONDS)
                except asyncio.TimeoutError:
                    try:
                        await asyncio.to_thread(app.state.sightings.flush_due)
                    except Exception:
                        logger.exception("Failed to save sightings")

        app.state.sightings_task = asyncio.create_task(_flush_sightings_periodically())
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
            # After the worker stops, so no detection can arrive after the flush.
            if hasattr(app.state, "robot_store"):
                app.state.robot_store.flush()
                app.state.robot_store.close()
            if hasattr(app.state, "sightings_task"):
                await app.state.sightings_task
            if hasattr(app.state, "sightings"):
                app.state.sightings.flush()
                app.state.sightings.close()


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
    app.include_router(history_router)

    @app.get("/health")
    async def health_check(request: Request) -> dict:
        state = request.app.state
        model_registry = getattr(state, "model_registry", None)
        robot_count = len(state.robot_store.get_all_robots()) if hasattr(state, "robot_store") else 0
        return {
            "status": "ok",
            "models": model_registry.list_models() if model_registry else [],
            "robot_count": robot_count,
        }

    return app


app = create_app()

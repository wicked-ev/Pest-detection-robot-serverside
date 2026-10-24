import asyncio
import threading
from typing import Any, Callable


async def run_in_daemon_thread(fn: Callable[..., Any], *args: Any, name: str = "background") -> Any:
    """Like asyncio.to_thread, but the thread does not keep the process alive.

    Python waits for asyncio.to_thread's threads before exiting. For a long job such as
    loading the model, that made the server hang when it was stopped mid-load (and an
    import running during interpreter shutdown can deadlock). A daemon thread is simply
    abandoned at exit instead, which is fine for work that saves nothing.
    """
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def deliver(setter: Callable[[Any], None], value: Any) -> None:
        if not future.done():  # the awaiting task may have been cancelled meanwhile
            setter(value)

    def target() -> None:
        try:
            result = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - handed to the awaiting task
            outcome = (future.set_exception, exc)
        else:
            outcome = (future.set_result, result)
        try:
            loop.call_soon_threadsafe(deliver, *outcome)
        except RuntimeError:
            pass  # event loop already closed (server shutting down)

    threading.Thread(target=target, name=name, daemon=True).start()
    return await future

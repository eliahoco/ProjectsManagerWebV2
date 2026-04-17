"""
Background task registry — prevents asyncio tasks from being garbage-collected
mid-execution.

Python docs: "Save a reference to the result of this function, to avoid a task
disappearing mid-execution."

Usage
-----
    from app.background import create_tracked_task, cancel_all_background_tasks

    # Fire-and-forget with guaranteed lifetime:
    create_tracked_task(some_coroutine(), name="descriptive-name")

    # On application shutdown:
    cancelled = await cancel_all_background_tasks()
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


def create_tracked_task(coro, name: str | None = None) -> asyncio.Task:
    """Create an asyncio task that is retained in a strong-reference set.

    The task is automatically removed from the set via a done-callback when it
    finishes, so the set never grows unbounded under normal operation.

    Args:
        coro: An awaitable (coroutine) to schedule.
        name: Optional task name for debugging (visible in asyncio.all_tasks()).

    Returns:
        The created :class:`asyncio.Task`.
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def cancel_all_background_tasks() -> int:
    """Cancel every tracked background task and wait for them to finish.

    Called from the application lifespan teardown to ensure a clean shutdown
    with no lingering coroutines.

    Returns:
        The number of tasks that were tracked at the time of cancellation.
    """
    count = len(_background_tasks)
    for task in list(_background_tasks):
        if not task.done():
            task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
    if count:
        logger.info(f"Cancelled {count} background task(s) on shutdown")
    return count

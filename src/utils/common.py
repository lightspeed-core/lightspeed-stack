"""Common utilities for the project."""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any


def run_once_async(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Ensure that an async function is executed only once.

    On the first invocation the wrapped coroutine is scheduled as an
    asyncio.Task on the current running event loop and its Task is cached.
    Later invocations return/await the same Task, receiving the same result or
    propagated exception. Requires an active running event loop when the
    wrapped function is first called.

    Returns:
        Any: The result produced by the wrapped coroutine, or the exception it
             raised propagated to callers.
    """
    task = None

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Run the wrapped async function exactly once and return its (awaited) result on every call.

        On the first invocation this schedules the underlying coroutine as an
        asyncio.Task on the current running event loop and caches that task.
        Subsequent calls return the same awaited task result. Exceptions raised
        by the task propagate to callers. Requires an active running event loop
        when first called.

        Returns:
            The awaited result of the wrapped coroutine.
        """
        nonlocal task
        if task is None:
            loop = asyncio.get_running_loop()
            task = loop.create_task(func(*args, **kwargs))
        return await task

    return wrapper

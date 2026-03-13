"""Step middleware pipeline.

Middleware wraps step execution with cross-cutting concerns like
logging, timeouts, retries, and error handling — without polluting
the executor or action code.

Usage:
    pipeline = MiddlewarePipeline()
    pipeline.add(LoggingMiddleware())
    pipeline.add(TimeoutMiddleware())
    pipeline.add(RetryMiddleware())
    result = pipeline.execute(step, params, context, action_fn)
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from autoflow.actions.base import ActionResult
from autoflow.engine.context import StepContext

log = logging.getLogger(__name__)

# Type alias for the callable that actually runs the action
ActionCallable = Callable[[dict, StepContext], ActionResult]


class StepMiddleware(ABC):
    """Base class for step middleware."""

    @abstractmethod
    def __call__(
        self,
        params: dict,
        context: StepContext,
        next_fn: ActionCallable,
        step_config: dict,
    ) -> ActionResult:
        """Execute middleware logic, calling next_fn to continue the chain.
        
        Args:
            params: User-defined step parameters
            context: Typed execution context
            next_fn: The next middleware or the actual action
            step_config: Step-level config (retry, timeout, etc.)
        """
        ...


class LoggingMiddleware(StepMiddleware):
    """Logs step start/end with timing."""

    def __call__(self, params, context, next_fn, step_config):
        step_name = step_config.get("name", "unnamed")
        action = step_config.get("action", "unknown")
        context.logger.info("  Running: %s (%s)", step_name, action)

        start = time.perf_counter()
        result = next_fn(params, context)
        elapsed = (time.perf_counter() - start) * 1000

        level = logging.INFO if result.success else logging.WARNING
        context.logger.log(level, "  %s: %s (%.1fms)", step_name, result.message, elapsed)
        return result


class TimeoutMiddleware(StepMiddleware):
    """Enforces a timeout on step execution using concurrent.futures.

    Uses a thread-based approach instead of SIGALRM so it works in both
    the main thread and worker threads (e.g., during parallel execution).
    """

    def __call__(self, params, context, next_fn, step_config):
        timeout = step_config.get("timeout")
        if not timeout or timeout <= 0:
            return next_fn(params, context)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(next_fn, params, context)
            try:
                return future.result(timeout=timeout)
            except (TimeoutError, FuturesTimeoutError):
                return ActionResult(
                    success=False,
                    message=f"Step timed out after {timeout}s",
                )


class RetryMiddleware(StepMiddleware):
    """Retries failed steps with configurable count and delay."""

    def __call__(self, params, context, next_fn, step_config):
        max_retries = step_config.get("retry", 0)
        retry_delay = step_config.get("retry_delay", 1.0)

        if max_retries <= 0:
            return next_fn(params, context)

        last_result = None
        for attempt in range(1, max_retries + 2):  # +1 for initial try, +1 for range
            last_result = next_fn(params, context)
            if last_result.success:
                if attempt > 1:
                    context.logger.info("  Succeeded on attempt %d/%d", attempt, max_retries + 1)
                return last_result

            if attempt <= max_retries:
                context.logger.warning(
                    "  Attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt, max_retries + 1, last_result.message, retry_delay,
                )
                time.sleep(retry_delay)

        context.logger.error("  All %d attempts failed", max_retries + 1)
        return last_result


class ErrorBoundaryMiddleware(StepMiddleware):
    """Catches unhandled exceptions and converts them to ActionResult."""

    def __call__(self, params, context, next_fn, step_config):
        try:
            return next_fn(params, context)
        except Exception as e:
            step_name = step_config.get("name", "unnamed")
            context.logger.error("  Step '%s' raised: %s", step_name, e, exc_info=True)
            return ActionResult(success=False, message=f"Unhandled error: {e}")


class MiddlewarePipeline:
    """Chains middleware into an execution pipeline.
    
    Middleware is applied in order: first added = outermost wrapper.
    The default pipeline is: ErrorBoundary → Logging → Timeout → Retry → Action
    """

    def __init__(self) -> None:
        self._middleware: List[StepMiddleware] = []

    def add(self, middleware: StepMiddleware) -> MiddlewarePipeline:
        """Add middleware to the pipeline. Returns self for chaining."""
        self._middleware.append(middleware)
        return self

    def execute(
        self,
        params: dict,
        context: StepContext,
        action_fn: ActionCallable,
        step_config: dict,
    ) -> ActionResult:
        """Execute the action through all middleware layers."""

        # Build chain from inside out: action_fn is the core,
        # each middleware wraps the next
        chain = action_fn
        for mw in reversed(self._middleware):
            prev = chain
            chain = lambda p, c, _mw=mw, _prev=prev: _mw(p, c, _prev, step_config)

        return chain(params, context)


def create_default_pipeline() -> MiddlewarePipeline:
    """Create the standard middleware pipeline.
    
    Order (outermost to innermost):
    1. ErrorBoundary — catches any unhandled exception
    2. Logging — logs timing and status
    3. Timeout — kills long-running steps
    4. Retry — retries on failure
    5. (action) — the actual step logic
    """
    return (
        MiddlewarePipeline()
        .add(ErrorBoundaryMiddleware())
        .add(LoggingMiddleware())
        .add(TimeoutMiddleware())
        .add(RetryMiddleware())
    )

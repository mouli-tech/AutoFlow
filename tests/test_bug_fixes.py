"""Tests for bug fixes across the AutoFlow codebase."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from autoflow.actions.base import ActionResult
from autoflow.engine.context import StepContext
from autoflow.engine.middleware import TimeoutMiddleware
from autoflow.engine.registry import ActionRegistry
from autoflow.actions.conditional import ConditionalAction


class TestTimeoutMiddlewareInThreads:
    """BUG 1: Verify TimeoutMiddleware works inside worker threads."""

    def test_timeout_triggers_on_slow_action(self):
        mw = TimeoutMiddleware()
        step_config = {"timeout": 1, "name": "test", "action": "test"}

        def slow_action(params, context):
            time.sleep(5)
            return ActionResult(success=True, message="done")

        result = mw({}, StepContext(), slow_action, step_config)
        assert not result.success
        assert "timed out" in result.message.lower()

    def test_timeout_works_in_worker_thread(self):
        """The actual bug scenario — called from a ThreadPoolExecutor worker."""
        mw = TimeoutMiddleware()
        step_config = {"timeout": 1, "name": "test", "action": "test"}

        def slow_action(params, context):
            time.sleep(5)
            return ActionResult(success=True, message="done")

        def run_in_thread():
            return mw({}, StepContext(), slow_action, step_config)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_thread)
            result = future.result(timeout=10)

        assert not result.success
        assert "timed out" in result.message.lower()

    def test_no_timeout_passes_through(self):
        mw = TimeoutMiddleware()
        step_config = {"timeout": 0, "name": "test", "action": "test"}

        def fast_action(params, context):
            return ActionResult(success=True, message="fast")

        result = mw({}, StepContext(), fast_action, step_config)
        assert result.success
        assert result.message == "fast"

    def test_fast_action_completes_before_timeout(self):
        mw = TimeoutMiddleware()
        step_config = {"timeout": 10, "name": "test", "action": "test"}

        def fast_action(params, context):
            return ActionResult(success=True, message="done quickly")

        result = mw({}, StepContext(), fast_action, step_config)
        assert result.success
        assert result.message == "done quickly"


class TestContextPropagation:
    """BUG 6: Verify nested steps receive parent context."""

    def test_execute_nested_steps_passes_parent_context(self):
        mock_executor = MagicMock()
        mock_executor.execute_steps.return_value = []

        parent_ctx = StepContext(
            variables={"parent_var": "parent_value"},
            executor=mock_executor,
        )

        from autoflow.engine.workflow import WorkflowStep
        steps = [WorkflowStep(action="notify", params={"message": "test"})]
        parent_ctx.execute_nested_steps(steps)

        mock_executor.execute_steps.assert_called_once_with(steps, context=parent_ctx)

    def test_nested_steps_can_read_parent_variables(self):
        mock_executor = MagicMock()
        mock_executor.execute_steps.return_value = []

        parent_ctx = StepContext(
            variables={"key": "value"},
            executor=mock_executor,
        )

        from autoflow.engine.workflow import WorkflowStep
        steps = [WorkflowStep(action="notify")]
        parent_ctx.execute_nested_steps(steps)

        # The context passed should have the parent's variables
        call_args = mock_executor.execute_steps.call_args
        assert call_args.kwargs["context"].variables["key"] == "value"

    def test_execute_nested_steps_raises_without_executor(self):
        ctx = StepContext(variables={})
        from autoflow.engine.workflow import WorkflowStep
        with pytest.raises(RuntimeError, match="No executor"):
            ctx.execute_nested_steps([WorkflowStep(action="test")])


class TestRegistryThreadSafety:
    """BUG 7: Verify ActionRegistry singleton is thread-safe."""

    def test_singleton_from_multiple_threads(self):
        # Reset singleton for test isolation
        original = ActionRegistry._instance
        ActionRegistry._instance = None
        try:
            instances = []
            barrier = threading.Barrier(10)

            def create_instance():
                barrier.wait()
                instances.append(id(ActionRegistry()))

            threads = [threading.Thread(target=create_instance) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(set(instances)) == 1
        finally:
            # Restore original singleton
            ActionRegistry._instance = original


class TestConditionalOperators:
    """BUG 11: Verify comparison operators with non-numeric values."""

    def test_numeric_greater_than(self):
        assert ConditionalAction._evaluate("count > 5", {"count": "10"}) is True
        assert ConditionalAction._evaluate("count > 5", {"count": "3"}) is False

    def test_numeric_less_than(self):
        assert ConditionalAction._evaluate("count < 5", {"count": "3"}) is True
        assert ConditionalAction._evaluate("count < 5", {"count": "10"}) is False

    def test_numeric_equality(self):
        assert ConditionalAction._evaluate("count == 5", {"count": "5"}) is True
        assert ConditionalAction._evaluate("count != 5", {"count": "3"}) is True

    def test_string_fallback_equality(self):
        assert ConditionalAction._evaluate("status == running", {"status": "running"}) is True
        assert ConditionalAction._evaluate("status != running", {"status": "stopped"}) is True

    def test_string_fallback_ordering(self):
        # After fix: ordering operators use string comparison for non-numeric values
        assert ConditionalAction._evaluate("status > active", {"status": "zebra"}) is True
        assert ConditionalAction._evaluate("status < zebra", {"status": "active"}) is True

    def test_missing_variable_returns_false(self):
        assert ConditionalAction._evaluate("missing > 5", {}) is False

    def test_boolean_truthy_check(self):
        assert ConditionalAction._evaluate("has_events", {"has_events": True}) is True
        assert ConditionalAction._evaluate("has_events", {"has_events": False}) is False
        assert ConditionalAction._evaluate("has_events", {}) is False

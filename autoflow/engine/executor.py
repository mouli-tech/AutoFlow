from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from autoflow.engine.context import StepContext
from autoflow.engine.middleware import MiddlewarePipeline, create_default_pipeline
from autoflow.engine.registry import registry
from autoflow.engine.workflow import Workflow, WorkflowStep

log = logging.getLogger(__name__)


@dataclass
class StepResult:
    step_name: str
    action: str
    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class ExecutionResult:
    workflow_name: str
    success: bool
    step_results: list = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str | None = None


class WorkflowExecutor:
    """Workflow executor with middleware pipeline, parallel execution, and DAG support.

    Changes from v1:
    - Uses StepContext instead of injecting _context/_executor into params
    - Middleware pipeline handles logging, timeout, retry, error boundary
    - Supports parallel steps via 'parallel' field
    - Supports DAG dependencies via 'depends_on' field
    - No more special-casing for conditional — it uses StepContext.execute_nested_steps()
    """

    def __init__(self, pipeline: Optional[MiddlewarePipeline] = None) -> None:
        self.pipeline = pipeline or create_default_pipeline()

    def execute(self, workflow: Workflow) -> ExecutionResult:
        log.info("Executing workflow: %s", workflow.name)
        start = time.perf_counter()

        # Build shared context with workflow-level variables
        context = StepContext(
            variables=dict(workflow.variables),
            logger=logging.getLogger(f"autoflow.workflow.{workflow.name}"),
            executor=self,
            workflow_name=workflow.name,
        )

        # Check if any steps use depends_on — if so, use DAG execution
        has_deps = any(s.depends_on for s in workflow.steps)
        if has_deps:
            step_results = self._execute_dag(workflow.steps, context)
        else:
            step_results = self._execute_sequential(workflow.steps, context)

        total_ms = (time.perf_counter() - start) * 1000
        overall_success = all(r.success for r in step_results)
        log.info("Workflow '%s' finished in %.1fms (success=%s)", workflow.name, total_ms, overall_success)

        return ExecutionResult(
            workflow_name=workflow.name,
            success=overall_success,
            step_results=step_results,
            total_duration_ms=total_ms,
        )

    def _execute_sequential(self, steps: List[WorkflowStep], context: StepContext) -> List[StepResult]:
        """Execute steps in order, respecting on_failure policy."""
        results = []
        for i, step in enumerate(steps):
            context.step_index = i

            # Handle parallel steps
            if step.parallel:
                parallel_results = self._execute_parallel(step.parallel, context)
                results.extend(parallel_results)
                if not all(r.success for r in parallel_results):
                    if step.on_failure == "stop":
                        break
                continue

            step_name = step.name or f"Step {i + 1}: {step.action}"
            result = self._execute_step(step, step_name, context)
            results.append(result)

            if not result.success and step.on_failure == "stop":
                log.warning("Stopping workflow at: %s", step_name)
                break

        return results

    def _execute_parallel(self, steps: List[WorkflowStep], context: StepContext) -> List[StepResult]:
        """Execute steps concurrently using ThreadPoolExecutor."""
        results: List[StepResult] = [None] * len(steps)  # type: ignore

        with ThreadPoolExecutor(max_workers=min(len(steps), 8)) as pool:
            future_to_idx = {}
            for i, step in enumerate(steps):
                step_name = step.name or f"Parallel {i + 1}: {step.action}"
                future = pool.submit(self._execute_step, step, step_name, context)
                future_to_idx[future] = i

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    step = steps[idx]
                    results[idx] = StepResult(
                        step_name=step.name or f"Parallel {idx + 1}",
                        action=step.action,
                        success=False,
                        message=f"Parallel execution failed: {e}",
                    )

        return results

    def _execute_dag(self, steps: List[WorkflowStep], context: StepContext) -> List[StepResult]:
        """Execute steps respecting depends_on ordering.

        Steps with no dependencies run first. Steps with depends_on wait
        until all named dependencies have completed successfully.
        """
        # Build name -> step mapping
        named_steps: Dict[str, WorkflowStep] = {}
        for step in steps:
            if step.name:
                named_steps[step.name] = step

        completed: Dict[str, StepResult] = {}
        remaining = list(steps)
        all_results: List[StepResult] = []
        max_iterations = len(steps) * 2  # safety valve

        iteration = 0
        while remaining and iteration < max_iterations:
            iteration += 1
            runnable = []
            still_waiting = []

            for step in remaining:
                deps = step.depends_on or []
                if all(d in completed for d in deps):
                    # Check if all deps succeeded
                    dep_failures = [d for d in deps if not completed[d].success]
                    if dep_failures:
                        step_name = step.name or step.action
                        result = StepResult(
                            step_name=step_name,
                            action=step.action,
                            success=False,
                            message=f"Skipped: dependencies failed: {', '.join(dep_failures)}",
                        )
                        all_results.append(result)
                        if step.name:
                            completed[step.name] = result
                    else:
                        runnable.append(step)
                else:
                    still_waiting.append(step)

            if not runnable and still_waiting:
                # Deadlock — unresolvable deps
                for step in still_waiting:
                    step_name = step.name or step.action
                    result = StepResult(
                        step_name=step_name,
                        action=step.action,
                        success=False,
                        message=f"Deadlock: unresolvable deps: {step.depends_on}",
                    )
                    all_results.append(result)
                break

            # Execute runnable steps (could be parallelized in future)
            for step in runnable:
                step_name = step.name or step.action
                result = self._execute_step(step, step_name, context)
                all_results.append(result)
                if step.name:
                    completed[step.name] = result

            remaining = still_waiting

        return all_results

    def _execute_step(self, step: WorkflowStep, step_name: str, context: StepContext) -> StepResult:
        """Execute a single step through the middleware pipeline."""
        start = time.perf_counter()

        try:
            action_cls = registry.get(step.action)
            action = action_cls()
            params = dict(step.params)

            # For conditional: inject step-level config into params
            # (the conditional action still needs these to know which branch to take)
            if step.action == "conditional":
                params["_condition"] = step.condition
                params["_then_steps"] = step.then or []
                params["_else_steps"] = step.else_steps or []

            # Build step config for middleware
            step_config = step.to_step_config()

            # Execute through middleware pipeline
            def action_fn(p: dict, ctx: StepContext):
                return action.execute(p, ctx)

            action_result = self.pipeline.execute(
                params=params,
                context=context,
                action_fn=action_fn,
                step_config=step_config,
            )

            # Merge action output data into shared context
            if action_result.data:
                context.update(action_result.data)

            duration_ms = (time.perf_counter() - start) * 1000
            return StepResult(
                step_name=step_name,
                action=step.action,
                success=action_result.success,
                message=action_result.message,
                data=action_result.data,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            log.error("Step '%s' failed: %s", step_name, e)
            return StepResult(
                step_name=step_name,
                action=step.action,
                success=False,
                message=str(e),
                duration_ms=duration_ms,
            )

    def execute_steps(self, steps: List[WorkflowStep], context: Optional[StepContext] = None) -> list:
        """Execute a list of steps (used for nested/conditional execution).

        If no context is provided, creates a minimal one.
        """
        if context is None:
            context = StepContext(executor=self)
        return self._execute_sequential(steps, context)

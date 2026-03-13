from __future__ import annotations

import logging
from typing import Any

from autoflow.actions.base import ActionResult, BaseAction, register_action

log = logging.getLogger(__name__)


@register_action("conditional")
class ConditionalAction(BaseAction):
    """Conditional branching action.

    Now uses StepContext for accessing shared variables and executing
    nested steps — no more _context/_executor in params.
    """

    def execute(self, params: dict, context=None) -> ActionResult:
        # Get condition and branch steps from params (set by executor)
        condition = params.get("_condition", "")
        then_steps = params.get("_then_steps", [])
        else_steps = params.get("_else_steps", [])

        # Get variables from context (preferred) or fallback to params
        variables = {}
        if context is not None:
            variables = context.variables
        elif "_context" in params:
            variables = params["_context"]

        if not condition:
            return ActionResult(success=False, message="No condition specified")

        result = self._evaluate(condition, variables)
        branch = "then" if result else "else"
        steps = then_steps if result else else_steps

        if steps and context is not None and context.executor is not None:
            from autoflow.engine.workflow import WorkflowStep

            workflow_steps = []
            for s in steps:
                if isinstance(s, WorkflowStep):
                    workflow_steps.append(s)
                elif isinstance(s, dict):
                    workflow_steps.append(WorkflowStep.model_validate(s))

            step_results = context.execute_nested_steps(workflow_steps)
            all_ok = all(r.success for r in step_results)
            return ActionResult(
                success=all_ok,
                message=f"{branch} branch: {len(step_results)} step(s)",
                data={"branch_taken": branch},
            )
        elif steps and "_executor" in params:
            # Backward compatibility: old-style executor in params
            from autoflow.engine.workflow import WorkflowStep
            executor = params["_executor"]

            workflow_steps = []
            for s in steps:
                if isinstance(s, WorkflowStep):
                    workflow_steps.append(s)
                elif isinstance(s, dict):
                    workflow_steps.append(WorkflowStep.model_validate(s))

            step_results = executor.execute_steps(workflow_steps)
            all_ok = all(r.success for r in step_results)
            return ActionResult(
                success=all_ok,
                message=f"{branch} branch: {len(step_results)} step(s)",
                data={"branch_taken": branch},
            )

        return ActionResult(success=True, message=f"{branch} branch: nothing to run", data={"branch_taken": branch})

    @staticmethod
    def _evaluate(condition: str, variables: dict) -> bool:
        condition = condition.strip()

        for op in [">=", "<=", "!=", "==", ">", "<"]:
            if op in condition:
                parts = condition.split(op, 1)
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    compare_val = parts[1].strip()
                    ctx_val = variables.get(var_name)
                    if ctx_val is None:
                        return False
                    try:
                        ctx_num = float(ctx_val)
                        cmp_num = float(compare_val)
                        ops = {">=": ctx_num >= cmp_num, "<=": ctx_num <= cmp_num, "!=": ctx_num != cmp_num,
                               "==": ctx_num == cmp_num, ">": ctx_num > cmp_num, "<": ctx_num < cmp_num}
                        return ops[op]
                    except (ValueError, TypeError):
                        str_val = str(ctx_val)
                        if op == "==":
                            return str_val == compare_val
                        elif op == "!=":
                            return str_val != compare_val
                        elif op == ">":
                            return str_val > compare_val
                        elif op == "<":
                            return str_val < compare_val
                        elif op == ">=":
                            return str_val >= compare_val
                        elif op == "<=":
                            return str_val <= compare_val
                        return False

        val = variables.get(condition)
        return bool(val) if val is not None else False

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.application.interfaces import UnitOfWork
from core.domain.agents.entities import Agent, AgentDecision, AgentRun
from core.domain.agents.enums import AgentRunStatus, AgentType
from core.domain.agents.interfaces import AgentPolicy, AgentRuntime, ToolGateway
from core.domain.agents.state_machine import (
    AgentRunStateMachine,
    InvalidAgentRunTransition,
)
from core.domain.events.entities import Event
from core.domain.llm.interfaces import LLMProvider, LLMRequest
from core.domain.tasks.entities import Task, TaskExecution
from core.domain.tasks.enums import TaskStatus
from core.infrastructure.metrics.execution import (
    aura_agent_iterations_total,
    aura_agent_run_duration_seconds,
    aura_agent_runs_total,
)


class CodingAgentRuntime(AgentRuntime):
    def __init__(
        self,
        uow: UnitOfWork,
        llm_provider: LLMProvider,
        tool_gateway: ToolGateway,
        agent_policy: AgentPolicy,
        agent: Agent,
    ):
        self.uow = uow
        self.llm_provider = llm_provider
        self.tool_gateway = tool_gateway
        self.agent_policy = agent_policy
        self.agent = agent

    async def run(
        self,
        task_id: UUID,
        task_execution_id: UUID,
        agent_id: UUID,
        worktree_path: str,
        repository_id: str,
    ) -> AgentRun:
        # Create agent run
        agent_run = AgentRun(
            mission_id=UUID(int=0),  # Will be filled from task
            task_id=task_id,
            task_execution_id=task_execution_id,
            agent_id=agent_id,
            max_iterations=self.agent_policy.max_iterations,
            max_tool_calls=self.agent_policy.max_tool_calls,
            max_runtime_seconds=self.agent_policy.max_runtime_seconds,
            max_failed_actions=self.agent_policy.max_failed_actions,
        )

        # Get mission_id from task
        async with self.uow:
            task = await self.uow.tasks.get(task_id)
            if task:
                agent_run.mission_id = task.mission_id
            await self.uow.agent_runs.create(agent_run)
            await self.uow.commit()

        # Transition to READY
        try:
            AgentRunStateMachine.transition(agent_run, AgentRunStatus.READY)
        except InvalidAgentRunTransition:
            pass

        async with self.uow:
            await self.uow.agent_runs.update(agent_run)
            await self.uow.events.append(
                Event(
                    event_type="agent.run.created",
                    mission_id=agent_run.mission_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    metadata={
                        "agent_run_id": str(agent_run.id),
                        "agent_type": self.agent.agent_type.value,
                    },
                )
            )
            await self.uow.commit()

        start_time = time.time()
        consecutive_failures = 0

        # Main agent loop
        while True:
            # Check timeout
            if time.time() - start_time > self.agent_policy.max_runtime_seconds:
                await self._fail_run(agent_run, "Runtime timeout exceeded")
                break

            # Check limits
            limit_error = self.agent_policy.check_limits(agent_run)
            if limit_error:
                await self._fail_run(agent_run, limit_error)
                break

            # Transition to RUNNING
            if agent_run.status == AgentRunStatus.READY:
                try:
                    AgentRunStateMachine.transition(agent_run, AgentRunStatus.RUNNING)
                    agent_run.started_at = self._utc_now()
                    async with self.uow:
                        await self.uow.agent_runs.update(agent_run)
                        await self.uow.events.append(
                            Event(
                                event_type="agent.run.started",
                                mission_id=agent_run.mission_id,
                                task_id=task_id,
                                agent_id=agent_id,
                                metadata={"agent_run_id": str(agent_run.id)},
                            )
                        )
                        await self.uow.commit()
                except InvalidAgentRunTransition:
                    pass

            # Get agent decision from LLM
            decision = await self._get_agent_decision(
                agent_run, worktree_path, repository_id
            )

            if not decision:
                await self._fail_run(agent_run, "Failed to get agent decision")
                break

            # Check for finish
            if decision.action_type == "FINISH_TASK":
                await self._complete_run(agent_run, decision)
                break

            # Validate decision schema
            if not self._validate_decision(decision):
                await self._handle_failed_action(agent_run, "Invalid decision schema")
                consecutive_failures += 1
                if consecutive_failures >= self.agent_policy.max_failed_actions:
                    await self._fail_run(agent_run, "Too many consecutive failures")
                    break
                continue

            # Execute tool via gateway
            tool_result = await self.tool_gateway.execute_tool(
                agent_run,
                decision.action_type,
                decision.arguments,
                worktree_path,
            )

            # Update agent run counters
            agent_run.iteration_count += 1
            agent_run.tool_call_count += 1
            agent_run.updated_at = self._utc_now()

            # Check tool result
            if not tool_result.success:
                consecutive_failures += 1
                if consecutive_failures >= self.agent_policy.max_failed_actions:
                    await self._fail_run(agent_run, "Too many failed tool calls")
                    break
            else:
                consecutive_failures = 0

            # Check if tool was a FINISH_TASK
            if tool_result.metadata.get("finish_task"):
                if tool_result.metadata.get("success", True):
                    await self._complete_run(agent_run, decision)
                else:
                    await self._fail_run(
                        agent_run, tool_result.output.get("summary", "Task failed")
                    )
                break

            # Update run
            async with self.uow:
                await self.uow.agent_runs.update(agent_run)
                await self.uow.commit()

        # Final update
        duration = time.time() - start_time
        aura_agent_run_duration_seconds.observe(duration)
        aura_agent_runs_total.inc()

        return agent_run

    async def _get_agent_decision(
        self, agent_run: AgentRun, worktree_path: str, repository_id: str
    ) -> Optional[AgentDecision]:
        # Build context for LLM
        system_prompt = self._build_system_prompt()
        user_prompt = await self._build_user_prompt(
            agent_run, worktree_path, repository_id
        )

        # Get previous tool results for context
        async with self.uow:
            tool_calls = await self.uow.tool_calls.get_by_agent_run(agent_run.id)

        # Build conversation history
        conversation = []
        for tc in tool_calls:
            if tc.status.value in ["COMPLETED", "FAILED"]:
                conversation.append(
                    f"Tool: {tc.tool_name}, Args: {tc.arguments}, Result: {tc.result_summary}, Error: {tc.failure_reason}"
                )

        if conversation:
            user_prompt += "\n\nPrevious Actions:\n" + "\n".join(conversation[-10:])

        request = LLMRequest(
            provider="default",
            model="gpt-4o-or-nim",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )

        try:
            response = await self.llm_provider.generate(request)
            data = json.loads(response.content)
            return AgentDecision(**data)
        except Exception as e:
            return None

    def _build_system_prompt(self) -> str:
        from core.domain.agents.tools import TOOL_SCHEMAS

        tools_desc = []
        for name, schema in TOOL_SCHEMAS.items():
            tools_desc.append(f"- {name}: {schema['description']}")

        return f"""You are the AURA Coding Agent.
Your job is to complete the assigned implementation task using ONLY the available tools.

Available Tools:
{chr(10).join(tools_desc)}

Rules:
1. You MUST output ONLY a valid JSON object matching the AgentDecision schema.
2. Do NOT output any explanatory text, only the JSON.
3. All file operations MUST stay within the assigned worktree.
4. You cannot execute arbitrary shell commands - use RUN_COMMAND tool which goes through the sandbox.
5. When the task is complete, use FINISH_TASK with a summary.

AgentDecision Schema:
{{
    "action_type": "READ_FILE|LIST_DIRECTORY|SEARCH_REPOSITORY|WRITE_FILE|RUN_COMMAND|GET_GIT_STATUS|GET_GIT_DIFF|RUN_TESTS|FINISH_TASK",
    "target": "description of target (file path, directory, etc.)",
    "arguments": {{...}},
    "rationale": "why you chose this action",
    "expected_result": "what you expect to happen",
    "confidence": 0.0-1.0,
    "correlation_id": "optional tracking id"
}}"""

    async def _build_user_prompt(
        self, agent_run: AgentRun, worktree_path: str, repository_id: str
    ) -> str:
        async with self.uow:
            task = await self.uow.tasks.get(agent_run.task_id)

        return f"""Task: {task.title if task else 'Unknown'}
Description: {task.description if task else 'Unknown'}
Worktree: {worktree_path}
Repository: {repository_id}

Current iteration: {agent_run.iteration_count + 1}/{self.agent_policy.max_iterations}
Tool calls: {agent_run.tool_call_count}/{self.agent_policy.max_tool_calls}

What is your next action?"""

    def _validate_decision(self, decision: AgentDecision) -> bool:
        from core.domain.agents.enums import ActionType

        try:
            ActionType(decision.action_type)
            return True
        except ValueError:
            return False

    async def _handle_failed_action(self, agent_run: AgentRun, reason: str):
        agent_run.updated_at = self._utc_now()
        async with self.uow:
            await self.uow.agent_runs.update(agent_run)
            await self.uow.events.append(
                Event(
                    event_type="agent.action.failed",
                    mission_id=agent_run.mission_id,
                    task_id=agent_run.task_id,
                    agent_id=agent_run.agent_id,
                    metadata={"agent_run_id": str(agent_run.id), "reason": reason},
                )
            )
            await self.uow.commit()

    async def _complete_run(self, agent_run: AgentRun, decision: AgentDecision):
        try:
            AgentRunStateMachine.transition(agent_run, AgentRunStatus.COMPLETED)
        except InvalidAgentRunTransition:
            try:
                AgentRunStateMachine.transition(agent_run, AgentRunStatus.VERIFYING)
                AgentRunStateMachine.transition(agent_run, AgentRunStatus.COMPLETED)
            except InvalidAgentRunTransition:
                pass

        agent_run.completed_at = self._utc_now()
        agent_run.final_result = decision.arguments.get("summary", "Task completed")
        agent_run.updated_at = self._utc_now()

        async with self.uow:
            await self.uow.agent_runs.update(agent_run)
            # Update task status
            task = await self.uow.tasks.get(agent_run.task_id)
            if task:
                task.status = TaskStatus.SUCCEEDED
                task.updated_at = self._utc_now()
                await self.uow.tasks.update(task)

            await self.uow.events.append(
                Event(
                    event_type="agent.run.completed",
                    mission_id=agent_run.mission_id,
                    task_id=agent_run.task_id,
                    agent_id=agent_run.agent_id,
                    metadata={
                        "agent_run_id": str(agent_run.id),
                        "result": agent_run.final_result,
                    },
                )
            )
            await self.uow.commit()

    async def _fail_run(self, agent_run: AgentRun, reason: str):
        try:
            AgentRunStateMachine.transition(agent_run, AgentRunStatus.FAILED)
        except InvalidAgentRunTransition:
            pass

        agent_run.completed_at = self._utc_now()
        agent_run.failure_reason = reason
        agent_run.updated_at = self._utc_now()

        async with self.uow:
            await self.uow.agent_runs.update(agent_run)
            # Update task status
            task = await self.uow.tasks.get(agent_run.task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.updated_at = self._utc_now()
                await self.uow.tasks.update(task)

            await self.uow.events.append(
                Event(
                    event_type="agent.run.failed",
                    mission_id=agent_run.mission_id,
                    task_id=agent_run.task_id,
                    agent_id=agent_run.agent_id,
                    metadata={
                        "agent_run_id": str(agent_run.id),
                        "failure_reason": reason,
                    },
                )
            )
            await self.uow.commit()

    def _utc_now(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

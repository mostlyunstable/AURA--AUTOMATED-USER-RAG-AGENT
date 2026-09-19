from prometheus_client import Counter, Histogram

# Environments
aura_execution_environments_created_total = Counter(
    "aura_execution_environments_created_total", "Total execution environments created"
)
aura_execution_environments_failed_total = Counter(
    "aura_execution_environments_failed_total",
    "Total execution environments that failed to create",
)
aura_execution_environments_destroyed_total = Counter(
    "aura_execution_environments_destroyed_total",
    "Total execution environments destroyed",
)
aura_cleanup_failures_total = Counter(
    "aura_cleanup_failures_total", "Total cleanup failures for execution environments"
)

# Worktrees
aura_worktrees_created_total = Counter(
    "aura_worktrees_created_total", "Total git worktrees created"
)
aura_worktrees_removed_total = Counter(
    "aura_worktrees_removed_total", "Total git worktrees removed"
)

# Commands
aura_commands_requested_total = Counter(
    "aura_commands_requested_total", "Total commands requested"
)
aura_commands_allowed_total = Counter(
    "aura_commands_allowed_total", "Total commands allowed by policy"
)
aura_commands_rejected_total = Counter(
    "aura_commands_rejected_total", "Total commands rejected by policy"
)
aura_commands_succeeded_total = Counter(
    "aura_commands_succeeded_total", "Total commands executed successfully"
)
aura_commands_failed_total = Counter(
    "aura_commands_failed_total", "Total commands failed"
)
aura_commands_timed_out_total = Counter(
    "aura_commands_timed_out_total", "Total commands timed out"
)
aura_command_duration_seconds = Histogram(
    "aura_command_duration_seconds", "Duration of command execution in seconds"
)
aura_command_output_truncated_total = Counter(
    "aura_command_output_truncated_total", "Total commands where output was truncated"
)

# Artifacts
aura_artifacts_created_total = Counter(
    "aura_artifacts_created_total", "Total artifacts collected successfully"
)
aura_artifacts_rejected_total = Counter(
    "aura_artifacts_rejected_total", "Total artifacts rejected"
)

# Agent Runs
aura_agent_runs_total = Counter("aura_agent_runs_total", "Total agent runs started")
aura_agent_runs_completed_total = Counter(
    "aura_agent_runs_completed_total", "Total agent runs completed successfully"
)
aura_agent_runs_failed_total = Counter(
    "aura_agent_runs_failed_total", "Total agent runs failed"
)
aura_agent_runs_timed_out_total = Counter(
    "aura_agent_runs_timed_out_total", "Total agent runs timed out"
)
aura_agent_run_duration_seconds = Histogram(
    "aura_agent_run_duration_seconds", "Duration of agent runs in seconds"
)

# Agent Iterations
aura_agent_iterations_total = Counter(
    "aura_agent_iterations_total", "Total agent iterations"
)

# Tool Calls
aura_agent_tool_calls_total = Counter(
    "aura_agent_tool_calls_total", "Total tool calls executed"
)
aura_agent_tool_rejections_total = Counter(
    "aura_agent_tool_rejections_total", "Total tool calls rejected by policy"
)
aura_agent_tool_failures_total = Counter(
    "aura_agent_tool_failures_total", "Total tool calls that failed"
)

# Verification
aura_verification_runs_total = Counter(
    "aura_verification_runs_total", "Total verification runs"
)
aura_verification_failures_total = Counter(
    "aura_verification_failures_total", "Total verification failures"
)
aura_verification_duration_seconds = Histogram(
    "aura_verification_duration_seconds", "Duration of verification runs in seconds"
)
aura_verification_checks_total = Counter(
    "aura_verification_checks_total", "Total verification checks performed"
)

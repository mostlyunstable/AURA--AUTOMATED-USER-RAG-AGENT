# Prompt Injection Handling

The Planner Agent separates Trusted AURA Context from Untrusted Repository/Forge Context.
The LLM is strictly instructed to disregard any imperative commands (e.g., "Run this script") found within the Repository or Forge memories. Furthermore, the Planner Agent possesses no capability to execute shell commands or git mutations.
Even if a prompt injection causes the LLM to output a malicious task, the task is strictly validated against the `TaskType` enum and cannot execute arbitrary shell commands.

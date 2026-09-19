from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    pass


class ToolOutput(BaseModel):
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# READ_FILE
class ReadFileInput(ToolInput):
    path: str


class ReadFileOutput(ToolOutput):
    output: Optional[str] = None


# LIST_DIRECTORY
class ListDirectoryInput(ToolInput):
    path: str = "."


class ListDirectoryOutput(ToolOutput):
    output: Optional[list] = None


# SEARCH_REPOSITORY
class SearchRepositoryInput(ToolInput):
    query: str
    path: str = "."
    max_results: int = 20


class SearchRepositoryOutput(ToolOutput):
    output: Optional[list] = None


# WRITE_FILE
class WriteFileInput(ToolInput):
    path: str
    content: str


class WriteFileOutput(ToolOutput):
    pass


# RUN_COMMAND
class RunCommandInput(ToolInput):
    executable: str
    arguments: list[str] = Field(default_factory=list)
    working_directory: str = "."
    timeout_seconds: int = 300


class RunCommandOutput(ToolOutput):
    output: Optional[dict] = None


# GET_GIT_STATUS
class GetGitStatusInput(ToolInput):
    path: str = "."


class GetGitStatusOutput(ToolOutput):
    output: Optional[str] = None


# GET_GIT_DIFF
class GetGitDiffInput(ToolInput):
    path: str = "."


class GetGitDiffOutput(ToolOutput):
    output: Optional[str] = None


# RUN_TESTS
class RunTestsInput(ToolInput):
    command: str = "pytest"
    arguments: list[str] = Field(default_factory=list)
    working_directory: str = "."
    timeout_seconds: int = 300


class RunTestsOutput(ToolOutput):
    output: Optional[dict] = None


# FINISH_TASK
class FinishTaskInput(ToolInput):
    summary: str
    success: bool = True


class FinishTaskOutput(ToolOutput):
    pass


# Tool definitions mapping
TOOL_SCHEMAS = {
    "READ_FILE": {
        "name": "READ_FILE",
        "description": "Read a file from the worktree",
        "input_schema": ReadFileInput.model_json_schema(),
        "output_schema": ReadFileOutput.model_json_schema(),
        "required_capability": "READ_REPOSITORY",
    },
    "LIST_DIRECTORY": {
        "name": "LIST_DIRECTORY",
        "description": "List directory contents",
        "input_schema": ListDirectoryInput.model_json_schema(),
        "output_schema": ListDirectoryOutput.model_json_schema(),
        "required_capability": "READ_REPOSITORY",
    },
    "SEARCH_REPOSITORY": {
        "name": "SEARCH_REPOSITORY",
        "description": "Search for content in the repository",
        "input_schema": SearchRepositoryInput.model_json_schema(),
        "output_schema": SearchRepositoryOutput.model_json_schema(),
        "required_capability": "SEARCH_REPOSITORY",
    },
    "WRITE_FILE": {
        "name": "WRITE_FILE",
        "description": "Write a file to the worktree",
        "input_schema": WriteFileInput.model_json_schema(),
        "output_schema": WriteFileOutput.model_json_schema(),
        "required_capability": "WRITE_REPOSITORY",
    },
    "RUN_COMMAND": {
        "name": "RUN_COMMAND",
        "description": "Execute a command in the sandbox",
        "input_schema": RunCommandInput.model_json_schema(),
        "output_schema": RunCommandOutput.model_json_schema(),
        "required_capability": "RUN_COMMAND",
    },
    "GET_GIT_STATUS": {
        "name": "GET_GIT_STATUS",
        "description": "Get git status of the worktree",
        "input_schema": GetGitStatusInput.model_json_schema(),
        "output_schema": GetGitStatusOutput.model_json_schema(),
        "required_capability": "READ_GIT",
    },
    "GET_GIT_DIFF": {
        "name": "GET_GIT_DIFF",
        "description": "Get git diff of the worktree",
        "input_schema": GetGitDiffInput.model_json_schema(),
        "output_schema": GetGitDiffOutput.model_json_schema(),
        "required_capability": "READ_GIT",
    },
    "RUN_TESTS": {
        "name": "RUN_TESTS",
        "description": "Run tests in the worktree",
        "input_schema": RunTestsInput.model_json_schema(),
        "output_schema": RunTestsOutput.model_json_schema(),
        "required_capability": "RUN_TESTS",
    },
    "FINISH_TASK": {
        "name": "FINISH_TASK",
        "description": "Signal task completion",
        "input_schema": FinishTaskInput.model_json_schema(),
        "output_schema": FinishTaskOutput.model_json_schema(),
        "required_capability": "FINISH_TASK",
    },
}

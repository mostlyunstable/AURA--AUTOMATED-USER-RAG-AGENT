import pytest

from core.domain.agents.enums import ActionType, AgentCapability
from core.domain.agents.tools import TOOL_SCHEMAS, ReadFileInput, WriteFileInput


def test_tool_schemas_exist():
    expected_tools = [
        "READ_FILE",
        "LIST_DIRECTORY",
        "SEARCH_REPOSITORY",
        "WRITE_FILE",
        "RUN_COMMAND",
        "GET_GIT_STATUS",
        "GET_GIT_DIFF",
        "RUN_TESTS",
        "FINISH_TASK",
    ]
    for tool in expected_tools:
        assert tool in TOOL_SCHEMAS
        assert "name" in TOOL_SCHEMAS[tool]
        assert "description" in TOOL_SCHEMAS[tool]
        assert "input_schema" in TOOL_SCHEMAS[tool]
        assert "output_schema" in TOOL_SCHEMAS[tool]
        assert "required_capability" in TOOL_SCHEMAS[tool]


def test_read_file_input():
    inp = ReadFileInput(path="test.py")
    assert inp.path == "test.py"


def test_write_file_input():
    inp = WriteFileInput(path="test.py", content="print('hello')")
    assert inp.path == "test.py"
    assert inp.content == "print('hello')"


def test_action_type_enum():
    assert ActionType.READ_FILE.value == "READ_FILE"
    assert ActionType.WRITE_FILE.value == "WRITE_FILE"
    assert ActionType.FINISH_TASK.value == "FINISH_TASK"


def test_agent_capability_enum():
    assert AgentCapability.READ_REPOSITORY.value == "READ_REPOSITORY"
    assert AgentCapability.WRITE_REPOSITORY.value == "WRITE_REPOSITORY"
    assert AgentCapability.RUN_COMMAND.value == "RUN_COMMAND"

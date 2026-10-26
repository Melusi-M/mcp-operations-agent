import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from mcp_operations_agent.agent import (
    AgentExecutionError,
    MCPClaudeAgent,
)
from mcp_operations_agent.audit import (
    JsonlAuditLogger,
)
from mcp_operations_agent.claude_gateway import (
    ClaudeTextBlock,
    ClaudeToolUseBlock,
    ClaudeTurn,
)
from mcp_operations_agent.database import (
    OperationsRepository,
)
from mcp_operations_agent.servers.database_server import (
    create_database_server,
)


class ScriptedClaudeGateway:
    def __init__(
        self,
        turns: list[ClaudeTurn],
    ) -> None:
        self.turns = list(turns)
        self.received_messages: list[
            list[dict[str, Any]]
        ] = []
        self.received_tools: list[
            list[dict[str, Any]]
        ] = []

    async def create_turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> ClaudeTurn:
        self.received_messages.append(
            list(messages)
        )
        self.received_tools.append(
            list(tools)
        )

        if not self.turns:
            raise RuntimeError(
                "No scripted Claude turn remains"
            )

        return self.turns.pop(0)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server(
    tmp_path: Path,
):
    repository = OperationsRepository(
        tmp_path / "operations.db"
    )
    repository.initialize()
    repository.seed_demo_data()

    return create_database_server(
        repository
    )


@pytest.mark.anyio
async def test_agent_discovers_and_executes_tool(
    server,
) -> None:
    claude = ScriptedClaudeGateway(
        [
            ClaudeTurn(
                stop_reason="tool_use",
                content=[
                    ClaudeToolUseBlock(
                        id="tool-1",
                        name="find_orders",
                        input={
                            "status": "pending",
                            "limit": 10,
                        },
                    ),
                ],
            ),
            ClaudeTurn(
                stop_reason="end_turn",
                content=[
                    ClaudeTextBlock(
                        text=(
                            "There is one pending order "
                            "worth R19,300."
                        )
                    ),
                ],
            ),
        ]
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=client,
        )

        answer = await agent.run(
            "Show me the pending orders."
        )

    assert answer == (
        "There is one pending order "
        "worth R19,300."
    )

    second_request_messages = (
        claude.received_messages[1]
    )
    tool_result_message = (
        second_request_messages[-1]
    )
    tool_result = (
        tool_result_message["content"][0]
    )

    assert tool_result["type"] == (
        "tool_result"
    )
    assert tool_result["tool_use_id"] == (
        "tool-1"
    )
    assert tool_result["is_error"] is False
    assert "19300.0" in tool_result["content"]


@pytest.mark.anyio
async def test_agent_passes_discovered_tools_to_claude(
    server,
) -> None:
    claude = ScriptedClaudeGateway(
        [
            ClaudeTurn(
                stop_reason="end_turn",
                content=[
                    ClaudeTextBlock(
                        text="No tool was required."
                    ),
                ],
            ),
        ]
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=client,
        )

        await agent.run(
            "Say that no tool was required."
        )

    tool_names = {
        tool["name"]
        for tool in claude.received_tools[0]
    }

    assert tool_names == {
        "list_customers",
        "get_customer",
        "find_orders",
    }


@pytest.mark.anyio
async def test_agent_rejects_unknown_tool(
    server,
) -> None:
    claude = ScriptedClaudeGateway(
        [
            ClaudeTurn(
                stop_reason="tool_use",
                content=[
                    ClaudeToolUseBlock(
                        id="tool-unknown",
                        name="delete_database",
                        input={},
                    ),
                ],
            ),
            ClaudeTurn(
                stop_reason="end_turn",
                content=[
                    ClaudeTextBlock(
                        text=(
                            "That operation is unavailable."
                        )
                    ),
                ],
            ),
        ]
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=client,
        )

        answer = await agent.run(
            "Delete the database."
        )

    assert answer == (
        "That operation is unavailable."
    )

    tool_result = (
        claude.received_messages[1]
        [-1]["content"][0]
    )

    assert tool_result["is_error"] is True
    assert (
        "not available"
        in tool_result["content"]
    )


@pytest.mark.anyio
async def test_agent_enforces_round_limit(
    server,
) -> None:
    repeated_turn = ClaudeTurn(
        stop_reason="tool_use",
        content=[
            ClaudeToolUseBlock(
                id="tool-repeat",
                name="list_customers",
                input={},
            ),
        ],
    )

    claude = ScriptedClaudeGateway(
        [
            repeated_turn,
            repeated_turn,
        ]
    )

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=client,
            maximum_rounds=2,
        )

        with pytest.raises(
            AgentExecutionError,
            match="maximum tool-use rounds",
        ):
            await agent.run(
                "Keep listing customers."
            )


@pytest.mark.anyio
async def test_agent_rejects_empty_prompt(
    server,
) -> None:
    claude = ScriptedClaudeGateway([])

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=client,
        )

        with pytest.raises(
            ValueError,
            match="cannot be empty",
        ):
            await agent.run("   ")

@pytest.mark.anyio
async def test_agent_audits_successful_tool_call(
    server,
    tmp_path: Path,
) -> None:
    claude = ScriptedClaudeGateway(
        [
            ClaudeTurn(
                stop_reason="tool_use",
                content=[
                    ClaudeToolUseBlock(
                        id="tool-audit",
                        name="find_orders",
                        input={
                            "status": "pending",
                        },
                    ),
                ],
            ),
            ClaudeTurn(
                stop_reason="end_turn",
                content=[
                    ClaudeTextBlock(
                        text="One pending order."
                    ),
                ],
            ),
        ]
    )

    audit_path = tmp_path / "audit.jsonl"

    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=client,
            audit_logger=JsonlAuditLogger(
                audit_path
            ),
        )

        await agent.run(
            "Show pending orders."
        )

    events = [
        json.loads(line)
        for line in audit_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    assert len(events) == 1
    assert events[0]["tool_name"] == (
        "find_orders"
    )
    assert events[0]["arguments"] == {
        "status": "pending",
    }
    assert events[0]["success"] is True
    assert events[0]["error"] is None
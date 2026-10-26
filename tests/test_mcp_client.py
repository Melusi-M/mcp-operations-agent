from pathlib import Path

import pytest
from mcp import Client

from mcp_operations_agent.database import (
    OperationsRepository,
)
from mcp_operations_agent.mcp_client import (
    MCPToolExecutionError,
    extract_text_content,
    list_all_tools,
    require_successful_result,
)
from mcp_operations_agent.servers.database_server import (
    create_database_server,
)


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
async def test_client_discovers_all_tools(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        tools = await list_all_tools(client)

    assert {
        tool.name
        for tool in tools
    } == {
        "list_customers",
        "get_customer",
        "find_orders",
    }


@pytest.mark.anyio
async def test_client_calls_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "find_orders",
            {
                "status": "pending",
                "limit": 10,
            },
        )

    validated_result = (
        require_successful_result(result)
    )
    orders = (
        validated_result
        .structured_content["result"]
    )

    assert len(orders) == 1
    assert orders[0]["order_id"] == 103


@pytest.mark.anyio
async def test_client_extracts_text_content(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "get_customer",
            {
                "customer_id": 1,
            },
        )

    text = extract_text_content(result)

    assert "Acme Estates" in text
    assert "operations@acme.test" in text


@pytest.mark.anyio
async def test_client_raises_for_tool_error(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "find_orders",
            {
                "status": "unknown",
            },
        )

    with pytest.raises(
        MCPToolExecutionError,
        match="Input should be",
    ):
        require_successful_result(result)
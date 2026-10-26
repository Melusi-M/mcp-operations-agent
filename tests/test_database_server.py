from pathlib import Path

import pytest
from mcp import Client

from mcp_operations_agent.database import (
    OperationsRepository,
)
from mcp_operations_agent.servers.database_server import (
    create_database_server,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def repository(
    tmp_path: Path,
) -> OperationsRepository:
    instance = OperationsRepository(
        tmp_path / "operations.db"
    )
    instance.initialize()
    instance.seed_demo_data()

    return instance


@pytest.fixture
def server(
    repository: OperationsRepository,
):
    return create_database_server(repository)


@pytest.mark.anyio
async def test_list_customers_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "list_customers",
            {
                "active_only": True,
                "limit": 10,
            },
        )

    assert result.is_error is False

    customers = (
        result.structured_content["result"]
    )

    assert len(customers) == 2
    assert all(
        customer["status"] == "active"
        for customer in customers
    )


@pytest.mark.anyio
async def test_get_customer_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "get_customer",
            {
                "customer_id": 2,
            },
        )

    assert result.is_error is False

    customer = (
        result.structured_content["result"]
    )

    assert customer["customer_id"] == 2
    assert customer["name"] == (
        "Ubuntu Property Group"
    )


@pytest.mark.anyio
async def test_get_unknown_customer_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "get_customer",
            {
                "customer_id": 999,
            },
        )

    assert result.is_error is False
    assert result.structured_content == {
        "result": None,
    }


@pytest.mark.anyio
async def test_find_orders_tool(
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

    assert result.is_error is False

    orders = result.structured_content["result"]

    assert len(orders) == 1
    assert orders[0]["order_id"] == 103
    assert orders[0]["customer_name"] == (
        "Ubuntu Property Group"
    )
    assert orders[0]["total_amount"] == 19300.0
    assert orders[0]["currency"] == "ZAR"


@pytest.mark.anyio
async def test_tool_rejects_invalid_limit(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "list_customers",
            {
                "limit": 101,
            },
        )

    assert result.is_error is True
    assert result.structured_content is None
    assert (
        "less than or equal to 100"
        in result.content[0].text
    )


@pytest.mark.anyio
async def test_tool_rejects_unknown_status(
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

    assert result.is_error is True
    assert result.structured_content is None
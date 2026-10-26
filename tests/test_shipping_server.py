import pytest
from mcp import Client

from mcp_operations_agent.servers.shipping_server import (
    create_shipping_server,
)
from mcp_operations_agent.shipping_api import (
    DemoShippingGateway,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server():
    return create_shipping_server(
        DemoShippingGateway()
    )


@pytest.mark.anyio
async def test_get_shipment_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "get_shipment",
            {
                "order_id": 101,
            },
        )

    assert result.is_error is False

    shipment = result.structured_content

    assert shipment is not None
    assert shipment["order_id"] == 101
    assert shipment["tracking_number"] == (
        "ZA-ACME-101"
    )
    assert shipment["status"] == "in_transit"


@pytest.mark.anyio
async def test_get_delivery_events_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "get_delivery_events",
            {
                "tracking_number": (
                    "ZA-ACME-101"
                ),
            },
        )

    assert result.is_error is False

    events = result.structured_content["result"]

    assert len(events) == 2
    assert events[-1]["status"] == (
        "in_transit"
    )


@pytest.mark.anyio
async def test_get_unknown_shipment_returns_error(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "get_shipment",
            {
                "order_id": 999,
            },
        )

    assert result.is_error is True
    assert result.structured_content is None


@pytest.mark.anyio
async def test_shipping_tools_are_read_only(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        page = await client.list_tools()

    assert len(page.tools) == 2

    assert all(
        tool.annotations is not None
        and (
            tool.annotations.read_only_hint
            is True
        )
        for tool in page.tools
    )

    assert all(
        tool.annotations is not None
        and (
            tool.annotations.open_world_hint
            is True
        )
        for tool in page.tools
    )
from pathlib import Path

import pytest
from mcp import Client

from mcp_operations_agent.database import (
    OperationsRepository,
)
from mcp_operations_agent.document_store import (
    DocumentStore,
)
from mcp_operations_agent.servers.database_server import (
    create_database_server,
)
from mcp_operations_agent.servers.filesystem_server import (
    create_filesystem_server,
)
from mcp_operations_agent.tool_router import (
    MCPToolRouter,
    ToolRoutingError,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def database_server(
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


@pytest.fixture
def filesystem_server(
    tmp_path: Path,
):
    root = tmp_path / "knowledge"
    root.mkdir()

    (root / "operations_policy.md").write_text(
        (
            "Pending orders must be reviewed "
            "within one business day."
        ),
        encoding="utf-8",
    )

    return create_filesystem_server(
        DocumentStore(root)
    )


@pytest.mark.anyio
async def test_router_namespaces_discovered_tools(
    database_server,
    filesystem_server,
) -> None:
    async with (
        Client(
            database_server,
            raise_exceptions=True,
        ) as database_client,
        Client(
            filesystem_server,
            raise_exceptions=True,
        ) as filesystem_client,
    ):
        router = MCPToolRouter(
            {
                "database": database_client,
                "knowledge": filesystem_client,
            }
        )

        page = await router.list_tools()

    assert {
        tool.name
        for tool in page.tools
    } == {
        "database__list_customers",
        "database__get_customer",
        "database__find_orders",
        "knowledge__list_documents",
        "knowledge__read_document",
        "knowledge__search_documents",
    }


@pytest.mark.anyio
async def test_router_calls_database_tool(
    database_server,
    filesystem_server,
) -> None:
    async with (
        Client(
            database_server,
            raise_exceptions=True,
        ) as database_client,
        Client(
            filesystem_server,
            raise_exceptions=True,
        ) as filesystem_client,
    ):
        router = MCPToolRouter(
            {
                "database": database_client,
                "knowledge": filesystem_client,
            }
        )

        await router.list_tools()

        result = await router.call_tool(
            "database__find_orders",
            {
                "status": "pending",
            },
        )

    orders = result.structured_content["result"]

    assert len(orders) == 1
    assert orders[0]["order_id"] == 103
    assert orders[0]["currency"] == "ZAR"


@pytest.mark.anyio
async def test_router_calls_knowledge_tool(
    database_server,
    filesystem_server,
) -> None:
    async with (
        Client(
            database_server,
            raise_exceptions=True,
        ) as database_client,
        Client(
            filesystem_server,
            raise_exceptions=True,
        ) as filesystem_client,
    ):
        router = MCPToolRouter(
            {
                "database": database_client,
                "knowledge": filesystem_client,
            }
        )

        await router.list_tools()

        result = await router.call_tool(
            "knowledge__search_documents",
            {
                "query": "pending orders",
            },
        )

    matches = result.structured_content["result"]

    assert len(matches) == 1
    assert matches[0]["relative_path"] == (
        "operations_policy.md"
    )


@pytest.mark.anyio
async def test_router_rejects_unknown_tool(
    database_server,
    filesystem_server,
) -> None:
    async with (
        Client(
            database_server,
            raise_exceptions=True,
        ) as database_client,
        Client(
            filesystem_server,
            raise_exceptions=True,
        ) as filesystem_client,
    ):
        router = MCPToolRouter(
            {
                "database": database_client,
                "knowledge": filesystem_client,
            }
        )

        await router.list_tools()

        with pytest.raises(
            ToolRoutingError,
            match="Unknown namespaced",
        ):
            await router.call_tool(
                "unknown__delete_everything",
                {},
            )
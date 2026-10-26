from pathlib import Path

import pytest
from mcp import Client

from mcp_operations_agent.document_store import (
    DocumentStore,
)
from mcp_operations_agent.servers.filesystem_server import (
    create_filesystem_server,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server(
    tmp_path: Path,
):
    root = tmp_path / "knowledge"
    root.mkdir()

    (root / "operations.md").write_text(
        (
            "Pending orders must be reviewed "
            "within one business day."
        ),
        encoding="utf-8",
    )

    store = DocumentStore(root)

    return create_filesystem_server(store)


@pytest.mark.anyio
async def test_list_documents_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "list_documents",
            {
                "relative_directory": ".",
                "limit": 10,
            },
        )

    assert result.is_error is False

    documents = (
        result.structured_content["result"]
    )

    assert len(documents) == 1
    assert documents[0]["relative_path"] == (
        "operations.md"
    )


@pytest.mark.anyio
async def test_read_document_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "read_document",
            {
                "relative_path": (
                    "operations.md"
                ),
            },
        )

    assert result.is_error is False

    document = result.structured_content

    assert document is not None
    assert document["relative_path"] == (
        "operations.md"
    )
    assert "Pending orders" in (
        document["content"]
    )


@pytest.mark.anyio
async def test_search_documents_tool(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "search_documents",
            {
                "query": "pending orders",
                "limit": 10,
            },
        )

    assert result.is_error is False

    matches = (
        result.structured_content["result"]
    )

    assert len(matches) == 1
    assert matches[0]["relative_path"] == (
        "operations.md"
    )


@pytest.mark.anyio
async def test_read_document_rejects_escape(
    server,
) -> None:
    async with Client(
        server,
        raise_exceptions=True,
    ) as client:
        result = await client.call_tool(
            "read_document",
            {
                "relative_path": (
                    "../secret.txt"
                ),
            },
        )

    assert result.is_error is True
    assert result.structured_content is None
import os
from pathlib import Path
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_operations_agent.document_store import (
    DocumentStore,
)
from mcp_operations_agent.models import (
    DocumentContent,
    DocumentMetadata,
    DocumentSearchMatch,
)


DEFAULT_KNOWLEDGE_ROOT = Path(
    os.getenv(
        "MCP_OPERATIONS_KNOWLEDGE_ROOT",
        "knowledge_base",
    )
)

DEFAULT_MAXIMUM_FILE_BYTES = int(
    os.getenv(
        "MCP_OPERATIONS_MAXIMUM_FILE_BYTES",
        "100000",
    )
)


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=False,
)


def create_filesystem_server(
    document_store: DocumentStore,
) -> MCPServer:
    """Create a read-only filesystem MCP server."""

    server = MCPServer(
        "Operations Knowledge Base"
    )

    @server.tool(
        title="List documents",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def list_documents(
        relative_directory: Annotated[
            str,
            Field(
                min_length=1,
                max_length=500,
                description=(
                    "Directory relative to the "
                    "approved knowledge root."
                ),
            ),
        ] = ".",
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description=(
                    "Maximum number of documents "
                    "to return."
                ),
            ),
        ] = 100,
    ) -> list[DocumentMetadata]:
        """List approved text documents."""

        return document_store.list_documents(
            relative_directory=relative_directory,
            limit=limit,
        )

    @server.tool(
        title="Read document",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def read_document(
        relative_path: Annotated[
            str,
            Field(
                min_length=1,
                max_length=500,
                description=(
                    "File path relative to the "
                    "approved knowledge root."
                ),
            ),
        ],
    ) -> DocumentContent:
        """Read one approved UTF-8 text document."""

        return document_store.read_document(
            relative_path
        )

    @server.tool(
        title="Search documents",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def search_documents(
        query: Annotated[
            str,
            Field(
                min_length=2,
                max_length=200,
                description=(
                    "Case-insensitive text to find "
                    "inside approved documents."
                ),
            ),
        ],
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=50,
                description=(
                    "Maximum number of matching "
                    "lines to return."
                ),
            ),
        ] = 20,
    ) -> list[DocumentSearchMatch]:
        """Search approved documents by text."""

        return document_store.search_documents(
            query,
            limit=limit,
        )

    return server


def create_default_document_store() -> DocumentStore:
    """Create the configured local document store."""

    document_store = DocumentStore(
        DEFAULT_KNOWLEDGE_ROOT,
        maximum_file_bytes=(
            DEFAULT_MAXIMUM_FILE_BYTES
        ),
    )
    document_store.initialize()

    return document_store


mcp = create_filesystem_server(
    create_default_document_store()
)


if __name__ == "__main__":
    mcp.run(
        transport="stdio"
    )
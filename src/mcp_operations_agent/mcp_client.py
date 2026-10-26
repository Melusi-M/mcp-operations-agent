import os
import asyncio
from pathlib import Path
from typing import Any, Protocol

from mcp import (
    Client,
    StdioServerParameters,
)
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

class MCPClientLike(Protocol):
    """Minimum client interface used by the agent."""

    async def list_tools(
        self,
        *,
        cursor: str | None = None,
    ) -> ListToolsResult:
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> CallToolResult:
        ...

class MCPToolExecutionError(RuntimeError):
    """Raised when an MCP tool returns an error result."""


async def list_all_tools(
    client: MCPClientLike,
) -> list[Tool]:
    """Retrieve every tool from a paginated MCP server."""

    tools: list[Tool] = []
    cursor: str | None = None

    while True:
        page = await client.list_tools(
            cursor=cursor
        )
        tools.extend(page.tools)

        if page.next_cursor is None:
            return tools

        cursor = page.next_cursor


def extract_text_content(
    result: CallToolResult,
) -> str:
    """Extract model-readable text from an MCP result."""

    text_blocks = [
        block.text
        for block in result.content
        if isinstance(block, TextContent)
    ]

    return "\n".join(text_blocks)


def require_successful_result(
    result: CallToolResult,
) -> CallToolResult:
    """Reject MCP tool results marked as errors."""

    if result.is_error:
        message = (
            extract_text_content(result)
            or "MCP tool execution failed"
        )

        raise MCPToolExecutionError(message)

    return result


def create_database_server_parameters(
) -> StdioServerParameters:
    """Describe how to launch the local database server."""

    project_root = (
        Path(__file__).resolve().parents[2]
    )
    server_path = (
        project_root
        / "src"
        / "mcp_operations_agent"
        / "servers"
        / "database_server.py"
    )

    return StdioServerParameters(
        command="uv",
        args=[
            "run",
            "mcp",
            "run",
            str(server_path),
        ],
        cwd=str(project_root),
    )

def create_filesystem_server_parameters(
    *,
    knowledge_root: str | Path = (
        "knowledge_base"
    ),
    maximum_file_bytes: int = 100_000,
) -> StdioServerParameters:
    """Describe how to launch the filesystem server."""

    if maximum_file_bytes <= 0:
        raise ValueError(
            "maximum_file_bytes must be "
            "greater than zero"
        )

    project_root = (
        Path(__file__).resolve().parents[2]
    )
    server_path = (
        project_root
        / "src"
        / "mcp_operations_agent"
        / "servers"
        / "filesystem_server.py"
    )

    environment = os.environ.copy()
    environment[
        "MCP_OPERATIONS_KNOWLEDGE_ROOT"
    ] = str(
        Path(knowledge_root).resolve()
    )
    environment[
        "MCP_OPERATIONS_MAXIMUM_FILE_BYTES"
    ] = str(maximum_file_bytes)

    return StdioServerParameters(
        command="uv",
        args=[
            "run",
            "mcp",
            "run",
            str(server_path),
        ],
        env=environment,
        cwd=str(project_root),
    )

async def run_client_demo() -> None:
    """Connect to the database server and call one tool."""

    parameters = (
        create_database_server_parameters()
    )

    async with Client(parameters) as client:
        server_name = (
            client.server_info.name
            if client.server_info is not None
            else "Unknown server"
        )

        print(
            f"Connected to: {server_name}"
        )
        print(
            "Protocol version: "
            f"{client.protocol_version}"
        )

        tools = await list_all_tools(client)

        print("Available tools:")

        for tool in tools:
            display_name = (
                tool.title
                or tool.name
            )
            print(
                f"- {tool.name}: {display_name}"
            )

        result = await client.call_tool(
            "find_orders",
            {
                "status": "pending",
                "limit": 10,
            },
        )

        require_successful_result(result)

        print("Pending orders:")
        print(result.structured_content)

def create_shipping_server_parameters(
    *,
    mode: str = "demo",
    base_url: str | None = None,
    api_key: str | None = None,
    timeout_seconds: float = 5.0,
    maximum_attempts: int = 2,
) -> StdioServerParameters:
    """Describe how to launch the shipping server."""

    normalized_mode = mode.strip().lower()

    if normalized_mode not in {
        "demo",
        "http",
    }:
        raise ValueError(
            "mode must be demo or http"
        )

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be "
            "greater than zero"
        )

    if not 1 <= maximum_attempts <= 3:
        raise ValueError(
            "maximum_attempts must be "
            "between 1 and 3"
        )

    if normalized_mode == "http":
        if not base_url or not base_url.strip():
            raise ValueError(
                "base_url is required in HTTP mode"
            )

        if not api_key or not api_key.strip():
            raise ValueError(
                "api_key is required in HTTP mode"
            )

    project_root = (
        Path(__file__).resolve().parents[2]
    )
    server_path = (
        project_root
        / "src"
        / "mcp_operations_agent"
        / "servers"
        / "shipping_server.py"
    )

    environment = os.environ.copy()
    environment[
        "MCP_OPERATIONS_SHIPPING_MODE"
    ] = normalized_mode
    environment[
        "MCP_OPERATIONS_SHIPPING_TIMEOUT_SECONDS"
    ] = str(timeout_seconds)
    environment[
        "MCP_OPERATIONS_SHIPPING_MAXIMUM_ATTEMPTS"
    ] = str(maximum_attempts)

    if base_url is not None:
        environment[
            "MCP_OPERATIONS_SHIPPING_API_BASE_URL"
        ] = base_url

    if api_key is not None:
        environment[
            "MCP_OPERATIONS_SHIPPING_API_KEY"
        ] = api_key

    return StdioServerParameters(
        command="uv",
        args=[
            "run",
            "mcp",
            "run",
            str(server_path),
        ],
        env=environment,
        cwd=str(project_root),
    )


def main() -> None:
    asyncio.run(
        run_client_demo()
    )


if __name__ == "__main__":
    main()
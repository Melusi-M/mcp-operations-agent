import re
from collections.abc import Mapping
from typing import Any

from mcp.types import (
    CallToolResult,
    ListToolsResult,
    Tool,
)

from mcp_operations_agent.mcp_client import (
    MCPClientLike,
    list_all_tools,
)


NAMESPACE_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*$"
)


class ToolRoutingError(RuntimeError):
    """Raised when an MCP tool cannot be routed safely."""


class MCPToolRouter:
    """Combines tools from multiple connected MCP clients."""

    def __init__(
        self,
        clients: Mapping[
            str,
            MCPClientLike,
        ],
    ) -> None:
        if not clients:
            raise ValueError(
                "At least one MCP client is required"
            )

        self.clients = dict(clients)
        self._routes: dict[
            str,
            tuple[MCPClientLike, str],
        ] = {}

        for namespace in self.clients:
            if not NAMESPACE_PATTERN.fullmatch(
                namespace
            ):
                raise ValueError(
                    "Invalid MCP namespace: "
                    f"{namespace}"
                )

            if "__" in namespace:
                raise ValueError(
                    "MCP namespaces cannot contain "
                    "double underscores"
                )

    async def list_tools(
        self,
        *,
        cursor: str | None = None,
    ) -> ListToolsResult:
        """Discover and namespace tools from all servers."""

        if cursor is not None:
            raise ToolRoutingError(
                "The combined tool router does not "
                "support external pagination cursors"
            )

        routed_tools: list[Tool] = []
        routes: dict[
            str,
            tuple[MCPClientLike, str],
        ] = {}

        for namespace, client in (
            self.clients.items()
        ):
            server_tools = await list_all_tools(
                client
            )

            for tool in server_tools:
                routed_name = (
                    f"{namespace}__{tool.name}"
                )

                if len(routed_name) > 64:
                    raise ToolRoutingError(
                        "Namespaced tool name exceeds "
                        f"64 characters: {routed_name}"
                    )

                if routed_name in routes:
                    raise ToolRoutingError(
                        "Duplicate routed tool name: "
                        f"{routed_name}"
                    )

                routes[routed_name] = (
                    client,
                    tool.name,
                )

                original_description = (
                    tool.description
                    or tool.title
                    or f"Execute {tool.name}."
                )

                routed_tools.append(
                    tool.model_copy(
                        update={
                            "name": routed_name,
                            "title": (
                                f"{namespace}: "
                                f"{tool.title or tool.name}"
                            ),
                            "description": (
                                f"[{namespace} server] "
                                f"{original_description}"
                            ),
                        }
                    )
                )

        self._routes = routes

        return ListToolsResult(
            tools=routed_tools,
            next_cursor=None,
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Route a namespaced tool call to its server."""

        route = self._routes.get(name)

        if route is None:
            raise ToolRoutingError(
                "Unknown namespaced MCP tool: "
                f"{name}"
            )

        client, original_tool_name = route

        return await client.call_tool(
            original_tool_name,
            arguments or {},
        )
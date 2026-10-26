from collections.abc import Sequence

from mcp.types import Tool


class ToolPolicyError(RuntimeError):
    """Raised when discovered MCP tools violate policy."""


def require_read_only_tools(
    tools: Sequence[Tool],
) -> None:
    """Reject tools not explicitly marked as read-only."""

    unsafe_tool_names = [
        tool.name
        for tool in tools
        if (
            tool.annotations is None
            or (
                tool.annotations.read_only_hint
                is not True
            )
        )
    ]

    if unsafe_tool_names:
        formatted_names = ", ".join(
            sorted(unsafe_tool_names)
        )

        raise ToolPolicyError(
            "The following MCP tools are not "
            "explicitly read-only: "
            f"{formatted_names}"
        )
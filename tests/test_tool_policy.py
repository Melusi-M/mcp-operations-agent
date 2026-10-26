import pytest
from mcp.types import (
    Tool,
    ToolAnnotations,
)

from mcp_operations_agent.tool_policy import (
    ToolPolicyError,
    require_read_only_tools,
)


def create_tool(
    *,
    name: str,
    read_only: bool | None,
) -> Tool:
    annotations = (
        None
        if read_only is None
        else ToolAnnotations(
            read_only_hint=read_only,
            open_world_hint=False,
        )
    )

    return Tool(
        name=name,
        description=f"Execute {name}.",
        input_schema={
            "type": "object",
            "properties": {},
        },
        annotations=annotations,
    )


def test_policy_accepts_read_only_tools() -> None:
    require_read_only_tools(
        [
            create_tool(
                name="list_customers",
                read_only=True,
            ),
            create_tool(
                name="find_orders",
                read_only=True,
            ),
        ]
    )


@pytest.mark.parametrize(
    "read_only",
    [
        False,
        None,
    ],
)
def test_policy_rejects_unsafe_tools(
    read_only: bool | None,
) -> None:
    with pytest.raises(
        ToolPolicyError,
        match="update_customer",
    ):
        require_read_only_tools(
            [
                create_tool(
                    name="update_customer",
                    read_only=read_only,
                )
            ]
        )
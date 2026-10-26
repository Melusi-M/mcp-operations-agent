from collections.abc import Sequence
from typing import (
    Annotated,
    Any,
    Literal,
    Protocol,
)

from anthropic import AsyncAnthropic
from mcp.types import Tool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ClaudeTextBlock(StrictModel):
    type: Literal["text"] = "text"
    text: str = Field(
        min_length=1,
    )


class ClaudeToolUseBlock(StrictModel):
    type: Literal["tool_use"] = "tool_use"
    id: str = Field(
        min_length=1,
    )
    name: str = Field(
        min_length=1,
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
    )


ClaudeContentBlock = Annotated[
    ClaudeTextBlock | ClaudeToolUseBlock,
    Field(discriminator="type"),
]


class ClaudeTurn(StrictModel):
    stop_reason: str = Field(
        min_length=1,
    )
    content: list[ClaudeContentBlock]


class ClaudeGateway(Protocol):
    async def create_turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> ClaudeTurn:
        ...


def convert_mcp_tools_to_claude(
    tools: Sequence[Tool],
) -> list[dict[str, Any]]:
    """Convert discovered MCP tools into Claude definitions."""

    return [
        {
            "name": tool.name,
            "description": (
                tool.description
                or tool.title
                or f"Execute {tool.name}."
            ),
            "input_schema": tool.input_schema,
        }
        for tool in tools
    ]


class AnthropicClaudeGateway:
    """Claude Messages API implementation."""

    def __init__(
        self,
        *,
        client: AsyncAnthropic,
        model: str,
        max_tokens: int = 2_000,
    ) -> None:
        if not model.strip():
            raise ValueError(
                "model cannot be empty"
            )

        if max_tokens <= 0:
            raise ValueError(
                "max_tokens must be greater than zero"
            )

        self.client = client
        self.model = model.strip()
        self.max_tokens = max_tokens

    async def create_turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> ClaudeTurn:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )

        content: list[
            ClaudeTextBlock | ClaudeToolUseBlock
        ] = []

        for block in response.content:
            if block.type == "text":
                if block.text.strip():
                    content.append(
                        ClaudeTextBlock(
                            text=block.text
                        )
                    )

            elif block.type == "tool_use":
                content.append(
                    ClaudeToolUseBlock(
                        id=block.id,
                        name=block.name,
                        input=dict(block.input),
                    )
                )

        return ClaudeTurn(
            stop_reason=(
                response.stop_reason
                or "unknown"
            ),
            content=content,
        )
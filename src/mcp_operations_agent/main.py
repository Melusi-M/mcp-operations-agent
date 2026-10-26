import argparse
import asyncio
from collections.abc import Sequence
from contextlib import AsyncExitStack

from anthropic import AsyncAnthropic
from mcp import Client

from mcp_operations_agent.agent import (
    MCPClaudeAgent,
)
from mcp_operations_agent.audit import (
    JsonlAuditLogger,
)
from mcp_operations_agent.claude_gateway import (
    AnthropicClaudeGateway,
)
from mcp_operations_agent.config import Settings
from mcp_operations_agent.mcp_client import (
    create_database_server_parameters,
    create_filesystem_server_parameters,
    create_shipping_server_parameters,
)
from mcp_operations_agent.tool_router import (
    MCPToolRouter,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ask Claude questions using tools "
            "discovered from MCP servers."
        )
    )

    parser.add_argument(
        "--question",
        required=True,
        help="Question for the operations agent",
    )

    return parser


async def run_agent(
    *,
    question: str,
    settings: Settings,
) -> str:
    anthropic_client = AsyncAnthropic(
        api_key=(
            settings
            .anthropic_api_key
            .get_secret_value()
        )
    )

    claude = AnthropicClaudeGateway(
        client=anthropic_client,
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
    )

    audit_logger = JsonlAuditLogger(
        settings.audit_log_path
    )

    database_parameters = (
        create_database_server_parameters()
    )

    filesystem_parameters = (
        create_filesystem_server_parameters(
            knowledge_root=(
                settings.knowledge_root
            ),
            maximum_file_bytes=(
                settings.maximum_file_bytes
            ),
        )
    )

    shipping_api_key = (
        settings.shipping_api_key.get_secret_value()
        if settings.shipping_api_key is not None
        else None
    )

    shipping_parameters = (
        create_shipping_server_parameters(
            mode=settings.shipping_mode,
            base_url=(
                settings.shipping_api_base_url
            ),
            api_key=shipping_api_key,
            timeout_seconds=(
                settings.shipping_timeout_seconds
            ),
            maximum_attempts=(
                settings.shipping_maximum_attempts
            ),
        )
    )

    async with AsyncExitStack() as stack:
        database_client = await (
            stack.enter_async_context(
                Client(database_parameters)
            )
        )

        filesystem_client = await (
            stack.enter_async_context(
                Client(filesystem_parameters)
            )
        )

        shipping_client = await (
            stack.enter_async_context(
                Client(shipping_parameters)
            )
        )

        tool_router = MCPToolRouter(
            {
                "database": database_client,
                "knowledge": filesystem_client,
                "shipping": shipping_client,
            }
        )

        agent = MCPClaudeAgent(
            claude=claude,
            mcp_client=tool_router,
            maximum_rounds=(
                settings.maximum_rounds
            ),
            tool_timeout_seconds=(
                settings.tool_timeout_seconds
            ),
            maximum_tool_result_chars=(
                settings.maximum_tool_result_chars
            ),
            audit_logger=audit_logger,
        )

        return await agent.run(question)


def main(
    arguments: Sequence[str] | None = None,
) -> int:
    parser = build_parser()
    parsed = parser.parse_args(arguments)
    settings = Settings()

    answer = asyncio.run(
        run_agent(
            question=parsed.question,
            settings=settings,
        )
    )

    print(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
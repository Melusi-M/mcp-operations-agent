import json
from time import perf_counter
from typing import Any

from mcp.types import CallToolResult

from mcp_operations_agent.audit import (
    AuditLogger,
    NullAuditLogger,
)
from mcp_operations_agent.claude_gateway import (
    ClaudeGateway,
    ClaudeTextBlock,
    ClaudeToolUseBlock,
    convert_mcp_tools_to_claude,
)
from mcp_operations_agent.mcp_client import (
    MCPClientLike,
    extract_text_content,
    list_all_tools,
)
from mcp_operations_agent.tool_policy import (
    require_read_only_tools,
)


SYSTEM_PROMPT = """
You are a read-only business operations assistant.

Use the available tools when the answer depends on
customer or order data.

Rules:
- Never invent customer or order information.
- Treat tool results as authoritative for this session.
- Do not claim that a tool succeeded when it returned
  an error.
- If a tool fails because of invalid arguments, correct
  the arguments and try again when possible.
- Do not request data unrelated to the user's question.
- Give a concise final answer.
""".strip()


class AgentExecutionError(RuntimeError):
    """Raised when the agent cannot finish safely."""


class MCPClaudeAgent:
    """Runs a bounded Claude and MCP tool-use loop."""

    def __init__(
        self,
        *,
        claude: ClaudeGateway,
        mcp_client: MCPClientLike,
        maximum_rounds: int = 5,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        if maximum_rounds <= 0:
            raise ValueError(
                "maximum_rounds must be greater than zero"
            )

        self.claude = claude
        self.mcp_client = mcp_client
        self.maximum_rounds = maximum_rounds
        self.audit_logger = (
            audit_logger
            or NullAuditLogger()
        )

    async def run(
        self,
        user_prompt: str,
    ) -> str:
        normalized_prompt = user_prompt.strip()

        if not normalized_prompt:
            raise ValueError(
                "user_prompt cannot be empty"
            )

        mcp_tools = await list_all_tools(
            self.mcp_client
        )

        require_read_only_tools(mcp_tools)

        available_tool_names = {
            tool.name
            for tool in mcp_tools
        }
        claude_tools = (
            convert_mcp_tools_to_claude(
                mcp_tools
            )
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": normalized_prompt,
            }
        ]

        for _round in range(
            self.maximum_rounds
        ):
            turn = await self.claude.create_turn(
                messages=messages,
                tools=claude_tools,
                system=SYSTEM_PROMPT,
            )

            assistant_content = [
                block.model_dump(mode="json")
                for block in turn.content
            ]

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                }
            )

            if turn.stop_reason == "end_turn":
                answer = self._extract_final_text(
                    turn.content
                )

                if not answer:
                    raise AgentExecutionError(
                        "Claude completed without "
                        "a final text response"
                    )

                return answer

            if turn.stop_reason != "tool_use":
                raise AgentExecutionError(
                    "Claude stopped with unsupported "
                    f"reason: {turn.stop_reason}"
                )

            tool_requests = [
                block
                for block in turn.content
                if isinstance(
                    block,
                    ClaudeToolUseBlock,
                )
            ]

            if not tool_requests:
                raise AgentExecutionError(
                    "Claude requested tool use without "
                    "providing a tool call"
                )

            tool_results: list[
                dict[str, Any]
            ] = []

            for request in tool_requests:
                result = await self._execute_tool(
                    request=request,
                    available_tool_names=(
                        available_tool_names
                    ),
                )
                tool_results.append(result)

            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )

        raise AgentExecutionError(
            "Agent exceeded the maximum tool-use rounds"
        )

    async def _execute_tool(
        self,
        *,
        request: ClaudeToolUseBlock,
        available_tool_names: set[str],
    ) -> dict[str, Any]:
        started_at = perf_counter()

        if request.name not in available_tool_names:
            error = (
                "The requested tool is not available."
            )

            self._record_tool_call(
                request=request,
                success=False,
                started_at=started_at,
                error=error,
            )

            return {
                "type": "tool_result",
                "tool_use_id": request.id,
                "content": error,
                "is_error": True,
            }

        try:
            result = await self.mcp_client.call_tool(
                request.name,
                request.input,
            )
        except Exception as error:
            self._record_tool_call(
                request=request,
                success=False,
                started_at=started_at,
                error=str(error),
            )
            raise

        error_message = None

        if result.is_error:
            error_message = (
                extract_text_content(result)
                or "The MCP tool returned an error."
            )

        self._record_tool_call(
            request=request,
            success=not result.is_error,
            started_at=started_at,
            error=error_message,
        )

        return {
            "type": "tool_result",
            "tool_use_id": request.id,
            "content": self._serialize_tool_result(
                result
            ),
            "is_error": result.is_error,
        }

    def _record_tool_call(
        self,
        *,
        request: ClaudeToolUseBlock,
        success: bool,
        started_at: float,
        error: str | None,
    ) -> None:
        duration_ms = int(
            (perf_counter() - started_at) * 1_000
        )

        self.audit_logger.record_tool_call(
            tool_name=request.name,
            tool_use_id=request.id,
            arguments=request.input,
            success=success,
            duration_ms=duration_ms,
            error=error,
        )

    @staticmethod
    def _serialize_tool_result(
        result: CallToolResult,
    ) -> str:
        if result.structured_content is not None:
            return json.dumps(
                result.structured_content,
                ensure_ascii=False,
            )

        text = extract_text_content(result)

        return (
            text
            or "The tool returned no content."
        )

    @staticmethod
    def _extract_final_text(
        content,
    ) -> str:
        text_parts = [
            block.text
            for block in content
            if isinstance(
                block,
                ClaudeTextBlock,
            )
        ]

        return "\n".join(
            text_parts
        ).strip()
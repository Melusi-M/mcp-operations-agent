import asyncio
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
customer, order, policy, or shipping data.

Rules:
- Never invent business information.
- Treat successful tool results as authoritative for
  this session.
- Do not claim that a tool succeeded when it returned
  an error.
- If a tool fails because of invalid arguments, correct
  the arguments and try again when possible.
- If a tool remains unavailable, clearly explain what
  could not be verified and provide only supported facts.
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
        tool_timeout_seconds: float = 10.0,
        maximum_tool_result_chars: int = 20_000,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        if maximum_rounds <= 0:
            raise ValueError(
                "maximum_rounds must be greater than zero"
            )

        if tool_timeout_seconds <= 0:
            raise ValueError(
                "tool_timeout_seconds must be "
                "greater than zero"
            )

        if maximum_tool_result_chars < 100:
            raise ValueError(
                "maximum_tool_result_chars must be "
                "at least 100"
            )

        self.claude = claude
        self.mcp_client = mcp_client
        self.maximum_rounds = maximum_rounds
        self.tool_timeout_seconds = (
            tool_timeout_seconds
        )
        self.maximum_tool_result_chars = (
            maximum_tool_result_chars
        )
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

            return self._create_error_result(
                request=request,
                message=error,
            )

        try:
            async with asyncio.timeout(
                self.tool_timeout_seconds
            ):
                result = (
                    await self.mcp_client.call_tool(
                        request.name,
                        request.input,
                    )
                )
        except TimeoutError:
            error = (
                "The tool call timed out before "
                "returning a result."
            )

            self._record_tool_call(
                request=request,
                success=False,
                started_at=started_at,
                error=error,
            )

            return self._create_error_result(
                request=request,
                message=error,
            )
        except Exception as exception:
            audit_error = (
                f"{type(exception).__name__}: "
                "MCP tool execution failed"
            )
            model_error = (
                "The tool could not be executed "
                "because of an internal service error."
            )

            self._record_tool_call(
                request=request,
                success=False,
                started_at=started_at,
                error=audit_error,
            )

            return self._create_error_result(
                request=request,
                message=model_error,
            )

        error_message = None

        if result.is_error:
            error_message = (
                extract_text_content(result)
                or "The MCP tool returned an error."
            )

        serialized_result = (
            self._serialize_tool_result(result)
        )
        bounded_result = self._bound_tool_content(
            serialized_result
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
            "content": bounded_result,
            "is_error": result.is_error,
        }

    def _bound_tool_content(
        self,
        content: str,
    ) -> str:
        if len(content) <= (
            self.maximum_tool_result_chars
        ):
            return content

        marker = (
            "\n...[TRUNCATED: tool result exceeded "
            "the configured size limit]"
        )

        available_characters = (
            self.maximum_tool_result_chars
            - len(marker)
        )

        if available_characters <= 0:
            return marker[
                :self.maximum_tool_result_chars
            ]

        return (
            content[:available_characters]
            + marker
        )

    @staticmethod
    def _create_error_result(
        *,
        request: ClaudeToolUseBlock,
        message: str,
    ) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": request.id,
            "content": message,
            "is_error": True,
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
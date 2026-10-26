import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Protocol


SENSITIVE_ARGUMENT_NAMES = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
}


def sanitize_audit_value(
    value: Any,
) -> Any:
    """Remove secrets and bound large values before logging."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}

        for key, item in value.items():
            normalized_key = str(key).lower()

            if any(
                sensitive_name in normalized_key
                for sensitive_name
                in SENSITIVE_ARGUMENT_NAMES
            ):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = (
                    sanitize_audit_value(item)
                )

        return sanitized

    if isinstance(value, list):
        return [
            sanitize_audit_value(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            sanitize_audit_value(item)
            for item in value
        ]

    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[TRUNCATED]"

    if value is None or isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    return str(value)


class AuditLogger(Protocol):
    """Records security-relevant MCP tool activity."""

    def record_tool_call(
        self,
        *,
        tool_name: str,
        tool_use_id: str,
        arguments: dict[str, Any],
        success: bool,
        duration_ms: int,
        error: str | None,
    ) -> None:
        ...


class NullAuditLogger:
    """No-op logger used when auditing is not configured."""

    def record_tool_call(
        self,
        *,
        tool_name: str,
        tool_use_id: str,
        arguments: dict[str, Any],
        success: bool,
        duration_ms: int,
        error: str | None,
    ) -> None:
        return None


class JsonlAuditLogger:
    """Writes one JSON audit event per line."""

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def record_tool_call(
        self,
        *,
        tool_name: str,
        tool_use_id: str,
        arguments: dict[str, Any],
        success: bool,
        duration_ms: int,
        error: str | None,
    ) -> None:
        event = {
            "timestamp": (
                datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "event_type": "mcp_tool_call",
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "arguments": sanitize_audit_value(
                arguments
            ),
            "success": success,
            "duration_ms": max(duration_ms, 0),
            "error": (
                sanitize_audit_value(error)
                if error is not None
                else None
            ),
        }

        serialized_event = json.dumps(
            event,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as audit_file:
                audit_file.write(serialized_event)
                audit_file.write("\n")
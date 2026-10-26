import json
from pathlib import Path

from mcp_operations_agent.audit import (
    JsonlAuditLogger,
    NullAuditLogger,
    sanitize_audit_value,
)


def test_sanitize_audit_value_redacts_secrets() -> None:
    result = sanitize_audit_value(
        {
            "customer_id": 2,
            "api_key": "secret-value",
            "nested": {
                "authorization_token": (
                    "bearer-secret"
                ),
            },
        }
    )

    assert result == {
        "customer_id": 2,
        "api_key": "[REDACTED]",
        "nested": {
            "authorization_token": "[REDACTED]",
        },
    }


def test_sanitize_audit_value_truncates_long_text() -> None:
    result = sanitize_audit_value(
        "A" * 600
    )

    assert len(result) < 600
    assert result.endswith("...[TRUNCATED]")


def test_jsonl_audit_logger_writes_event(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    logger = JsonlAuditLogger(audit_path)

    logger.record_tool_call(
        tool_name="find_orders",
        tool_use_id="tool-1",
        arguments={
            "status": "pending",
            "api_key": "do-not-record",
        },
        success=True,
        duration_ms=12,
        error=None,
    )

    lines = audit_path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 1

    event = json.loads(lines[0])

    assert event["event_type"] == "mcp_tool_call"
    assert event["tool_name"] == "find_orders"
    assert event["tool_use_id"] == "tool-1"
    assert event["arguments"] == {
        "status": "pending",
        "api_key": "[REDACTED]",
    }
    assert event["success"] is True
    assert event["duration_ms"] == 12
    assert event["error"] is None
    assert event["timestamp"].endswith("Z")


def test_null_audit_logger_accepts_event() -> None:
    logger = NullAuditLogger()

    logger.record_tool_call(
        tool_name="find_orders",
        tool_use_id="tool-1",
        arguments={},
        success=True,
        duration_ms=1,
        error=None,
    )
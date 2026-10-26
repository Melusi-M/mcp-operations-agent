import pytest
from pathlib import Path
from pydantic import ValidationError

from mcp_operations_agent.config import (
    Settings,
)


def test_settings_read_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_MODEL",
        "test-model",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_MAX_TOKENS",
        "1500",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_MAXIMUM_ROUNDS",
        "4",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_KNOWLEDGE_ROOT",
        "custom-knowledge",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_MAXIMUM_FILE_BYTES",
        "250000",
    )

    settings = Settings(
        _env_file=None
    )


    assert (
        settings
        .anthropic_api_key
        .get_secret_value()
        == "test-api-key"
    )
    assert settings.anthropic_model == (
        "test-model"
    )
    assert settings.max_tokens == 1_500
    assert settings.maximum_rounds == 4
    assert settings.knowledge_root == Path(
        "custom-knowledge"
    )
    assert settings.maximum_file_bytes == 250_000


def test_settings_require_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "ANTHROPIC_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ValidationError,
        match="ANTHROPIC_API_KEY",
    ):
        Settings(
            _env_file=None
        )


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        (
            "MCP_OPERATIONS_MAX_TOKENS",
            "0",
        ),
        (
            "MCP_OPERATIONS_MAXIMUM_ROUNDS",
            "11",
        ),
    ],
)
def test_settings_reject_invalid_limits(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        variable,
        value,
    )

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None
        )
def test_settings_accept_http_shipping_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY",
        "test-anthropic-key",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_SHIPPING_MODE",
        "http",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_SHIPPING_API_BASE_URL",
        "https://shipping.test",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_SHIPPING_API_KEY",
        "test-shipping-key",
    )

    settings = Settings(
        _env_file=None
    )

    assert settings.shipping_mode == "http"
    assert settings.shipping_api_base_url == (
        "https://shipping.test"
    )
    assert (
        settings.shipping_api_key is not None
    )
    assert (
        settings.shipping_api_key
        .get_secret_value()
        == "test-shipping-key"
    )
def test_settings_reject_incomplete_http_shipping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ANTHROPIC_API_KEY",
        "test-anthropic-key",
    )
    monkeypatch.setenv(
        "MCP_OPERATIONS_SHIPPING_MODE",
        "http",
    )
    monkeypatch.delenv(
        "MCP_OPERATIONS_SHIPPING_API_BASE_URL",
        raising=False,
    )
    monkeypatch.delenv(
        "MCP_OPERATIONS_SHIPPING_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ValidationError,
        match=(
            "SHIPPING_API_BASE_URL"
        ),
    ):
        Settings(
            _env_file=None
        )
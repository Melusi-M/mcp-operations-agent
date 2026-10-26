from pathlib import Path
from typing import Literal

from pydantic import (
    Field,
    SecretStr,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """Validated application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: SecretStr = Field(
        validation_alias="ANTHROPIC_API_KEY",
    )
    anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        min_length=1,
        validation_alias="MCP_OPERATIONS_MODEL",
    )
    max_tokens: int = Field(
        default=1_000,
        gt=0,
        le=8_000,
        validation_alias=(
            "MCP_OPERATIONS_MAX_TOKENS"
        ),
    )
    maximum_rounds: int = Field(
        default=5,
        gt=0,
        le=10,
        validation_alias=(
            "MCP_OPERATIONS_MAXIMUM_ROUNDS"
        ),
    )
    audit_log_path: Path = Field(
        default=Path(
            "run_logs/mcp_tool_audit.jsonl"
        ),
        validation_alias=(
            "MCP_OPERATIONS_AUDIT_LOG_PATH"
        ),
    )
    knowledge_root: Path = Field(
        default=Path("knowledge_base"),
        validation_alias=(
            "MCP_OPERATIONS_KNOWLEDGE_ROOT"
        ),
    )
    maximum_file_bytes: int = Field(
        default=100_000,
        gt=0,
        le=1_000_000,
        validation_alias=(
            "MCP_OPERATIONS_MAXIMUM_FILE_BYTES"
        ),
    )
    shipping_mode: Literal[
        "demo",
        "http",
    ] = Field(
        default="demo",
        validation_alias=(
            "MCP_OPERATIONS_SHIPPING_MODE"
        ),
    )
    shipping_api_base_url: str | None = Field(
        default=None,
        validation_alias=(
            "MCP_OPERATIONS_SHIPPING_API_BASE_URL"
        ),
    )
    shipping_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=(
            "MCP_OPERATIONS_SHIPPING_API_KEY"
        ),
    )
    shipping_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=30,
        validation_alias=(
            "MCP_OPERATIONS_SHIPPING_TIMEOUT_SECONDS"
        ),
    )
    tool_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=120,
        validation_alias=(
            "MCP_OPERATIONS_TOOL_TIMEOUT_SECONDS"
        ),
    )
    maximum_tool_result_chars: int = Field(
        default=20_000,
        ge=100,
        le=200_000,
        validation_alias=(
            "MCP_OPERATIONS_MAXIMUM_TOOL_RESULT_CHARS"
        ),
    )
    shipping_maximum_attempts: int = Field(
        default=2,
        ge=1,
        le=3,
        validation_alias=(
            "MCP_OPERATIONS_SHIPPING_MAXIMUM_ATTEMPTS"
        ),
    )
    @model_validator(mode="after")
    def validate_shipping_configuration(
        self,
    ) -> "Settings":
        if self.shipping_mode == "demo":
            return self

        if (
            self.shipping_api_base_url is None
            or not self.shipping_api_base_url.strip()
        ):
            raise ValueError(
                "MCP_OPERATIONS_SHIPPING_API_BASE_URL "
                "is required in HTTP mode"
            )

        if (
            self.shipping_api_key is None
            or not (
                self.shipping_api_key
                .get_secret_value()
                .strip()
            )
        ):
            raise ValueError(
                "MCP_OPERATIONS_SHIPPING_API_KEY "
                "is required in HTTP mode"
            )

        return self
import asyncio
import re
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import (
    TypeAdapter,
    ValidationError,
)

from mcp_operations_agent.models import (
    DeliveryEvent,
    Shipment,
)


TRACKING_NUMBER_PATTERN = re.compile(
    r"^[A-Za-z0-9-]{3,100}$"
)


class ShippingAPIError(RuntimeError):
    """Base error for safe shipping API failures."""


class ShipmentNotFoundError(
    ShippingAPIError
):
    """Raised when a shipment does not exist."""


class ShippingAPIUnavailableError(
    ShippingAPIError
):
    """Raised when the upstream API is unavailable."""


class ShippingGateway(Protocol):
    """Read-only shipping information contract."""

    async def get_shipment(
        self,
        order_id: int,
    ) -> Shipment:
        ...

    async def get_delivery_events(
        self,
        tracking_number: str,
    ) -> list[DeliveryEvent]:
        ...


class DemoShippingGateway:
    """Deterministic shipping data for local demos."""

    def __init__(self) -> None:
        self._shipments = {
            101: Shipment(
                order_id=101,
                tracking_number="ZA-ACME-101",
                carrier="Ubuntu Express",
                status="in_transit",
                estimated_delivery=(
                    "2026-10-28"
                ),
            ),
            102: Shipment(
                order_id=102,
                tracking_number="ZA-ACME-102",
                carrier="Ubuntu Express",
                status="delivered",
                estimated_delivery=(
                    "2026-09-26"
                ),
            ),
        }

        self._events = {
            "ZA-ACME-101": [
                DeliveryEvent(
                    tracking_number=(
                        "ZA-ACME-101"
                    ),
                    status="label_created",
                    description=(
                        "Shipping label created."
                    ),
                    occurred_at=(
                        "2026-10-01T10:00:00Z"
                    ),
                    location="Johannesburg",
                ),
                DeliveryEvent(
                    tracking_number=(
                        "ZA-ACME-101"
                    ),
                    status="in_transit",
                    description=(
                        "Shipment departed the "
                        "Johannesburg facility."
                    ),
                    occurred_at=(
                        "2026-10-02T06:30:00Z"
                    ),
                    location="Johannesburg",
                ),
            ],
            "ZA-ACME-102": [
                DeliveryEvent(
                    tracking_number=(
                        "ZA-ACME-102"
                    ),
                    status="delivered",
                    description=(
                        "Shipment delivered."
                    ),
                    occurred_at=(
                        "2026-09-26T13:10:00Z"
                    ),
                    location="Pretoria",
                ),
            ],
        }

    async def get_shipment(
        self,
        order_id: int,
    ) -> Shipment:
        if order_id <= 0:
            raise ValueError(
                "order_id must be greater than zero"
            )

        shipment = self._shipments.get(order_id)

        if shipment is None:
            raise ShipmentNotFoundError(
                "Shipment was not found"
            )

        return shipment

    async def get_delivery_events(
        self,
        tracking_number: str,
    ) -> list[DeliveryEvent]:
        normalized_tracking_number = (
            validate_tracking_number(
                tracking_number
            )
        )

        events = self._events.get(
            normalized_tracking_number
        )

        if events is None:
            raise ShipmentNotFoundError(
                "Shipment events were not found"
            )

        return list(events)


class HttpShippingGateway:
    """Validated HTTP shipping API adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 5.0,
        maximum_attempts: int = 2,
        retry_delay_seconds: float = 0.1,
    ) -> None:
        normalized_base_url = (
            base_url.strip().rstrip("/")
        )

        parsed_url = httpx.URL(
            normalized_base_url
        )

        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.host
        ):
            raise ValueError(
                "base_url must be a valid "
                "HTTP or HTTPS URL"
            )

        if (
            parsed_url.username
            or parsed_url.password
        ):
            raise ValueError(
                "base_url must not contain credentials"
            )

        if not api_key.strip():
            raise ValueError(
                "api_key cannot be empty"
            )

        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be "
                "greater than zero"
            )

        if not 1 <= maximum_attempts <= 3:
            raise ValueError(
                "maximum_attempts must be "
                "between 1 and 3"
            )

        if retry_delay_seconds < 0:
            raise ValueError(
                "retry_delay_seconds cannot "
                "be negative"
            )

        self.base_url = normalized_base_url
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.maximum_attempts = maximum_attempts
        self.retry_delay_seconds = (
            retry_delay_seconds
        )
        self.client = (
            client
            or httpx.AsyncClient()
        )
        self._owns_client = client is None

    async def get_shipment(
        self,
        order_id: int,
    ) -> Shipment:
        if order_id <= 0:
            raise ValueError(
                "order_id must be greater than zero"
            )

        payload = await self._get_json(
            f"/shipments/orders/{order_id}"
        )

        try:
            return Shipment.model_validate(
                payload
            )
        except ValidationError as error:
            raise ShippingAPIError(
                "Shipping API returned an "
                "invalid shipment response"
            ) from error

    async def get_delivery_events(
        self,
        tracking_number: str,
    ) -> list[DeliveryEvent]:
        normalized_tracking_number = (
            validate_tracking_number(
                tracking_number
            )
        )
        encoded_tracking_number = quote(
            normalized_tracking_number,
            safe="",
        )

        payload = await self._get_json(
            "/shipments/"
            f"{encoded_tracking_number}"
            "/events"
        )

        try:
            return TypeAdapter(
                list[DeliveryEvent]
            ).validate_python(payload)
        except ValidationError as error:
            raise ShippingAPIError(
                "Shipping API returned invalid "
                "delivery events"
            ) from error

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _get_json(
        self,
        path: str,
    ):
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(
            1,
            self.maximum_attempts + 1,
        ):
            try:
                response = await self.client.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": (
                            f"Bearer {self.api_key}"
                        ),
                    },
                    timeout=self.timeout_seconds,
                )
            except httpx.RequestError as error:
                last_error = error

                if attempt < self.maximum_attempts:
                    await self._wait_before_retry(
                        attempt
                    )
                    continue

                raise ShippingAPIUnavailableError(
                    "Shipping API is unavailable"
                ) from error

            if response.status_code == 404:
                raise ShipmentNotFoundError(
                    "Shipment was not found"
                )

            if (
                response.status_code == 429
                or response.status_code >= 500
            ):
                last_error = ShippingAPIUnavailableError(
                    "Shipping API returned a "
                    "temporary failure"
                )

                if attempt < self.maximum_attempts:
                    await self._wait_before_retry(
                        attempt
                    )
                    continue

                raise ShippingAPIUnavailableError(
                    "Shipping API is unavailable"
                )

            if response.status_code >= 400:
                raise ShippingAPIError(
                    "Shipping API rejected the request "
                    f"with status {response.status_code}"
                )

            try:
                return response.json()
            except ValueError as error:
                raise ShippingAPIError(
                    "Shipping API returned invalid JSON"
                ) from error

        raise ShippingAPIUnavailableError(
            "Shipping API is unavailable"
        ) from last_error

    async def _wait_before_retry(
        self,
        attempt: int,
    ) -> None:
        if self.retry_delay_seconds == 0:
            return

        await asyncio.sleep(
            self.retry_delay_seconds * attempt
        )


def validate_tracking_number(
    tracking_number: str,
) -> str:
    normalized_tracking_number = (
        tracking_number.strip()
    )

    if not TRACKING_NUMBER_PATTERN.fullmatch(
        normalized_tracking_number
    ):
        raise ValueError(
            "tracking_number contains "
            "unsupported characters"
        )

    return normalized_tracking_number
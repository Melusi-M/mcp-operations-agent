import httpx
import pytest

from mcp_operations_agent.shipping_api import (
    DemoShippingGateway,
    HttpShippingGateway,
    ShipmentNotFoundError,
    ShippingAPIError,
    ShippingAPIUnavailableError,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_demo_gateway_gets_shipment() -> None:
    gateway = DemoShippingGateway()

    shipment = await gateway.get_shipment(101)

    assert shipment.order_id == 101
    assert shipment.tracking_number == (
        "ZA-ACME-101"
    )
    assert shipment.status == "in_transit"


@pytest.mark.anyio
async def test_demo_gateway_gets_delivery_events(
) -> None:
    gateway = DemoShippingGateway()

    events = await gateway.get_delivery_events(
        "ZA-ACME-101"
    )

    assert len(events) == 2
    assert events[-1].status == "in_transit"


@pytest.mark.anyio
async def test_demo_gateway_rejects_unknown_order(
) -> None:
    gateway = DemoShippingGateway()

    with pytest.raises(
        ShipmentNotFoundError,
        match="not found",
    ):
        await gateway.get_shipment(999)


@pytest.mark.anyio
async def test_http_gateway_validates_shipment(
) -> None:
    received_authorization = None

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal received_authorization

        received_authorization = (
            request.headers.get(
                "Authorization"
            )
        )

        return httpx.Response(
            200,
            json={
                "order_id": 101,
                "tracking_number": (
                    "ZA-ACME-101"
                ),
                "carrier": "Ubuntu Express",
                "status": "in_transit",
                "estimated_delivery": (
                    "2026-10-28"
                ),
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        gateway = HttpShippingGateway(
            base_url="https://shipping.test",
            api_key="test-secret-key",
            client=client,
            retry_delay_seconds=0,
        )

        shipment = await gateway.get_shipment(
            101
        )

    assert shipment.order_id == 101
    assert received_authorization == (
        "Bearer test-secret-key"
    )


@pytest.mark.anyio
async def test_http_gateway_validates_events(
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "tracking_number": (
                        "ZA-ACME-101"
                    ),
                    "status": "in_transit",
                    "description": (
                        "Shipment departed."
                    ),
                    "occurred_at": (
                        "2026-10-02T06:30:00Z"
                    ),
                    "location": "Johannesburg",
                }
            ],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        gateway = HttpShippingGateway(
            base_url="https://shipping.test",
            api_key="test-secret-key",
            client=client,
            retry_delay_seconds=0,
        )

        events = (
            await gateway.get_delivery_events(
                "ZA-ACME-101"
            )
        )

    assert len(events) == 1
    assert events[0].status == "in_transit"


@pytest.mark.anyio
async def test_http_gateway_maps_not_found(
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            404,
            json={"message": "Not found"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        gateway = HttpShippingGateway(
            base_url="https://shipping.test",
            api_key="test-secret-key",
            client=client,
            retry_delay_seconds=0,
        )

        with pytest.raises(
            ShipmentNotFoundError,
            match="not found",
        ):
            await gateway.get_shipment(999)


@pytest.mark.anyio
async def test_http_gateway_retries_server_error(
) -> None:
    attempts = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            503,
            json={"message": "Unavailable"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        gateway = HttpShippingGateway(
            base_url="https://shipping.test",
            api_key="test-secret-key",
            client=client,
            maximum_attempts=2,
            retry_delay_seconds=0,
        )

        with pytest.raises(
            ShippingAPIUnavailableError,
            match="unavailable",
        ):
            await gateway.get_shipment(101)

    assert attempts == 2


@pytest.mark.anyio
async def test_http_gateway_rejects_invalid_payload(
) -> None:
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "order_id": 101,
                "status": "unsupported",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        gateway = HttpShippingGateway(
            base_url="https://shipping.test",
            api_key="test-secret-key",
            client=client,
            retry_delay_seconds=0,
        )

        with pytest.raises(
            ShippingAPIError,
            match="invalid shipment",
        ):
            await gateway.get_shipment(101)
def test_http_gateway_rejects_url_credentials(
) -> None:
    with pytest.raises(
        ValueError,
        match="must not contain credentials",
    ):
        HttpShippingGateway(
            base_url=(
                "https://user:password@shipping.test"
            ),
            api_key="test-secret-key",
        )
import os
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_operations_agent.models import (
    DeliveryEvent,
    Shipment,
)
from mcp_operations_agent.shipping_api import (
    DemoShippingGateway,
    HttpShippingGateway,
    ShippingGateway,
)


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=True,
)


def create_shipping_server(
    gateway: ShippingGateway,
) -> MCPServer:
    """Create a read-only shipping API MCP server."""

    server = MCPServer(
        "Operations Shipping API"
    )

    @server.tool(
        title="Get shipment",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_shipment(
        order_id: Annotated[
            int,
            Field(
                gt=0,
                description=(
                    "Positive operations order "
                    "identifier."
                ),
            ),
        ],
    ) -> Shipment:
        """Get shipment information for an order."""

        return await gateway.get_shipment(
            order_id
        )

    @server.tool(
        title="Get delivery events",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    async def get_delivery_events(
        tracking_number: Annotated[
            str,
            Field(
                min_length=3,
                max_length=100,
                pattern=(
                    r"^[A-Za-z0-9-]+$"
                ),
                description=(
                    "Tracking number returned by "
                    "the shipping service."
                ),
            ),
        ],
    ) -> list[DeliveryEvent]:
        """Get delivery events for a shipment."""

        return await gateway.get_delivery_events(
            tracking_number
        )

    return server


def create_default_shipping_gateway(
) -> ShippingGateway:
    """Create the configured shipping gateway."""

    mode = os.getenv(
        "MCP_OPERATIONS_SHIPPING_MODE",
        "demo",
    ).strip().lower()

    if mode == "demo":
        return DemoShippingGateway()

    if mode == "http":
        base_url = os.getenv(
            "MCP_OPERATIONS_SHIPPING_API_BASE_URL",
            "",
        ).strip()
        api_key = os.getenv(
            "MCP_OPERATIONS_SHIPPING_API_KEY",
            "",
        ).strip()

        if not base_url:
            raise RuntimeError(
                "MCP_OPERATIONS_SHIPPING_API_BASE_URL "
                "is required in HTTP mode"
            )

        if not api_key:
            raise RuntimeError(
                "MCP_OPERATIONS_SHIPPING_API_KEY "
                "is required in HTTP mode"
            )

        timeout_seconds = float(
            os.getenv(
                "MCP_OPERATIONS_SHIPPING_TIMEOUT_SECONDS",
                "5",
            )
        )
        maximum_attempts = int(
            os.getenv(
                "MCP_OPERATIONS_SHIPPING_MAXIMUM_ATTEMPTS",
                "2",
            )
        )

        return HttpShippingGateway(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            maximum_attempts=maximum_attempts,
        )

    raise RuntimeError(
        "Unsupported shipping mode: "
        f"{mode}"
    )


mcp = create_shipping_server(
    create_default_shipping_gateway()
)


if __name__ == "__main__":
    mcp.run(
        transport="stdio"
    )
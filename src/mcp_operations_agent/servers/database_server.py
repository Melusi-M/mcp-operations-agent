import os
from pathlib import Path
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_operations_agent.database import (
    OperationsRepository,
)
from mcp_operations_agent.models import (
    Customer,
    Order,
)


DEFAULT_DATABASE_PATH = Path(
    os.getenv(
        "MCP_OPERATIONS_DATABASE_PATH",
        "data/operations.db",
    )
)


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=False,
)


def create_database_server(
    repository: OperationsRepository,
) -> MCPServer:
    """Create an MCP server backed by a repository."""

    server = MCPServer(
        "Operations Database"
    )

    @server.tool(
        title="List customers",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def list_customers(
        active_only: Annotated[
            bool,
            Field(
                description=(
                    "Return only active customers "
                    "when true."
                )
            ),
        ] = False,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description=(
                    "Maximum number of customers "
                    "to return."
                ),
            ),
        ] = 20,
    ) -> list[Customer]:
        """List customers stored in the operations database."""

        return repository.list_customers(
            active_only=active_only,
            limit=limit,
        )

    @server.tool(
        title="Get customer",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_customer(
        customer_id: Annotated[
            int,
            Field(
                gt=0,
                description=(
                    "Unique positive customer identifier."
                ),
            ),
        ],
    ) -> Customer | None:
        """Find one customer by their unique identifier."""

        return repository.get_customer(
            customer_id
        )

    @server.tool(
        title="Find orders",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def find_orders(
        customer_id: Annotated[
            int | None,
            Field(
                gt=0,
                description=(
                    "Optional customer identifier "
                    "used to filter orders."
                ),
            ),
        ] = None,
        status: Annotated[
            Literal[
                "pending",
                "processing",
                "shipped",
                "delivered",
                "cancelled",
            ]
            | None,
            Field(
                description=(
                    "Optional order status filter."
                ),
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description=(
                    "Maximum number of orders "
                    "to return."
                ),
            ),
        ] = 20,
    ) -> list[Order]:
        """Find orders using optional customer and status filters."""

        return repository.find_orders(
            customer_id=customer_id,
            status=status,
            limit=limit,
        )

    return server


def create_default_repository(
) -> OperationsRepository:
    """Create the repository used by the local server."""

    repository = OperationsRepository(
        DEFAULT_DATABASE_PATH
    )
    repository.initialize()
    repository.seed_demo_data()

    return repository


mcp = create_database_server(
    create_default_repository()
)


if __name__ == "__main__":
    mcp.run(
        transport="stdio"
    )
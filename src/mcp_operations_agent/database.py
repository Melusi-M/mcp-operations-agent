import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp_operations_agent.models import (
    Customer,
    Order,
)


class OperationsRepository:
    """Provides read-only access to operations data."""

    def __init__(
        self,
        database_path: str | Path,
    ) -> None:
        self.database_path = Path(database_path)

    @contextmanager
    def _connect(
        self,
    ) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path
        )
        connection.row_factory = sqlite3.Row

        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the database schema when it is missing."""

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK (
                        status IN (
                            'active',
                            'inactive'
                        )
                    )
                );

                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN (
                            'pending',
                            'processing',
                            'shipped',
                            'delivered',
                            'cancelled'
                        )
                    ),
                    total_amount REAL NOT NULL CHECK (
                        total_amount >= 0
                    ),
                    currency TEXT NOT NULL DEFAULT 'ZAR' CHECK (currency IN ('ZAR')),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (customer_id)
                        REFERENCES customers(customer_id)
                );
                """
            )
            order_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(orders)"
                ).fetchall()
            }

            if "currency" not in order_columns:
                connection.execute(
                    """
                    ALTER TABLE orders
                    ADD COLUMN currency TEXT
                    NOT NULL DEFAULT 'ZAR'
                    CHECK (currency IN ('ZAR'))
                    """
                )
            connection.commit()

    def seed_demo_data(self) -> None:
        """Insert deterministic records for development."""

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO customers (
                    customer_id,
                    name,
                    email,
                    status
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        1,
                        "Acme Estates",
                        "operations@acme.test",
                        "active",
                    ),
                    (
                        2,
                        "Ubuntu Property Group",
                        "admin@ubuntu-property.test",
                        "active",
                    ),
                    (
                        3,
                        "Legacy Lettings",
                        "support@legacy-lettings.test",
                        "inactive",
                    ),
                ],
            )

            connection.executemany(
                """
                INSERT OR IGNORE INTO orders (
                    order_id,
                    customer_id,
                    status,
                    total_amount,
                    currency,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        101,
                        1,
                        "processing",
                        12500.00,
                        "ZAR",
                        "2026-10-01T09:00:00Z",
                    ),
                    (
                        102,
                        1,
                        "delivered",
                        8750.50,
                        "ZAR",
                        "2026-09-24T11:30:00Z",
                    ),
                    (
                        103,
                        2,
                        "pending",
                        19300.00,
                        "ZAR",
                        "2026-10-03T14:15:00Z",
                    ),
                    (
                        104,
                        3,
                        "cancelled",
                        4200.00,
                        "ZAR",
                        "2026-09-18T08:45:00Z",
                    ),
                ],
            )

            connection.commit()

    def list_customers(
        self,
        *,
        active_only: bool = False,
        limit: int = 20,
    ) -> list[Customer]:
        if not 1 <= limit <= 100:
            raise ValueError(
                "limit must be between 1 and 100"
            )

        query = """
            SELECT
                customer_id,
                name,
                email,
                status
            FROM customers
        """
        parameters: list[object] = []

        if active_only:
            query += " WHERE status = ?"
            parameters.append("active")

        query += " ORDER BY customer_id LIMIT ?"
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).fetchall()

        return [
            Customer.model_validate(dict(row))
            for row in rows
        ]

    def get_customer(
        self,
        customer_id: int,
    ) -> Customer | None:
        if customer_id <= 0:
            raise ValueError(
                "customer_id must be greater than zero"
            )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    customer_id,
                    name,
                    email,
                    status
                FROM customers
                WHERE customer_id = ?
                """,
                (customer_id,),
            ).fetchone()

        if row is None:
            return None

        return Customer.model_validate(dict(row))

    def find_orders(
        self,
        *,
        customer_id: int | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Order]:
        if customer_id is not None and customer_id <= 0:
            raise ValueError(
                "customer_id must be greater than zero"
            )

        allowed_statuses = {
            "pending",
            "processing",
            "shipped",
            "delivered",
            "cancelled",
        }

        if (
            status is not None
            and status not in allowed_statuses
        ):
            raise ValueError(
                "Unsupported order status"
            )

        if not 1 <= limit <= 100:
            raise ValueError(
                "limit must be between 1 and 100"
            )

        conditions: list[str] = []
        parameters: list[object] = []

        if customer_id is not None:
            conditions.append(
                "orders.customer_id = ?"
            )
            parameters.append(customer_id)

        if status is not None:
            conditions.append(
                "orders.status = ?"
            )
            parameters.append(status)

        query = """
            SELECT
                orders.order_id,
                orders.customer_id,
                customers.name AS customer_name,
                orders.status,
                orders.total_amount,
                orders.currency,
                orders.created_at
            FROM orders
            INNER JOIN customers
                ON customers.customer_id
                = orders.customer_id
        """

        if conditions:
            query += (
                " WHERE "
                + " AND ".join(conditions)
            )

        query += (
            " ORDER BY orders.created_at DESC"
            " LIMIT ?"
        )
        parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(
                query,
                parameters,
            ).fetchall()

        return [
            Order.model_validate(dict(row))
            for row in rows
        ]
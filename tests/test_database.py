from pathlib import Path

import pytest

from mcp_operations_agent.database import (
    OperationsRepository,
)


@pytest.fixture
def repository(
    tmp_path: Path,
) -> OperationsRepository:
    instance = OperationsRepository(
        tmp_path / "operations.db"
    )
    instance.initialize()
    instance.seed_demo_data()

    return instance


def test_repository_lists_all_customers(
    repository: OperationsRepository,
) -> None:
    customers = repository.list_customers()

    assert len(customers) == 3
    assert customers[0].name == "Acme Estates"
    assert customers[2].status == "inactive"


def test_repository_filters_active_customers(
    repository: OperationsRepository,
) -> None:
    customers = repository.list_customers(
        active_only=True
    )

    assert len(customers) == 2
    assert all(
        customer.status == "active"
        for customer in customers
    )


def test_repository_gets_customer_by_id(
    repository: OperationsRepository,
) -> None:
    customer = repository.get_customer(2)

    assert customer is not None
    assert customer.name == (
        "Ubuntu Property Group"
    )


def test_repository_returns_none_for_unknown_customer(
    repository: OperationsRepository,
) -> None:
    assert repository.get_customer(999) is None


def test_repository_finds_pending_orders(
    repository: OperationsRepository,
) -> None:
    orders = repository.find_orders(
        status="pending"
    )

    assert len(orders) == 1
    assert orders[0].order_id == 103
    assert orders[0].customer_name == (
        "Ubuntu Property Group"
    )
    assert orders[0].total_amount == 19300.00
    assert orders[0].currency == "ZAR"


def test_repository_filters_orders_by_customer(
    repository: OperationsRepository,
) -> None:
    orders = repository.find_orders(
        customer_id=1
    )

    assert len(orders) == 2
    assert all(
        order.customer_id == 1
        for order in orders
    )


@pytest.mark.parametrize(
    ("method", "message"),
    [
        (
            lambda repository: (
                repository.list_customers(
                    limit=0
                )
            ),
            "limit",
        ),
        (
            lambda repository: (
                repository.get_customer(0)
            ),
            "customer_id",
        ),
        (
            lambda repository: (
                repository.find_orders(
                    status="unknown"
                )
            ),
            "Unsupported order status",
        ),
    ],
)
def test_repository_rejects_invalid_arguments(
    repository: OperationsRepository,
    method,
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        method(repository)

def test_repository_migrates_existing_orders_with_currency(
    tmp_path: Path,
) -> None:
    import sqlite3

    database_path = tmp_path / "legacy.db"

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                total_amount REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            INSERT INTO customers (
                customer_id,
                name,
                email,
                status
            )
            VALUES (
                1,
                'Existing Customer',
                'existing@example.test',
                'active'
            );

            INSERT INTO orders (
                order_id,
                customer_id,
                status,
                total_amount,
                created_at
            )
            VALUES (
                1,
                1,
                'pending',
                500.00,
                '2026-10-01T10:00:00Z'
            );
            """
        )

    repository = OperationsRepository(
        database_path
    )
    repository.initialize()

    orders = repository.find_orders()

    assert len(orders) == 1
    assert orders[0].currency == "ZAR"
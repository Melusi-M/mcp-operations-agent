from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CurrencyCode = Literal["ZAR"]


class StrictModel(BaseModel):
    """Base model for validated application data."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class Customer(StrictModel):
    customer_id: int = Field(
        gt=0,
    )
    name: str = Field(
        min_length=1,
        max_length=200,
    )
    email: str = Field(
        min_length=3,
        max_length=320,
    )
    status: Literal[
        "active",
        "inactive",
    ]


class Order(StrictModel):
    order_id: int = Field(
        gt=0,
    )
    customer_id: int = Field(
        gt=0,
    )
    customer_name: str = Field(
        min_length=1,
        max_length=200,
    )
    status: Literal[
        "pending",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
    ]
    total_amount: float = Field(
        ge=0,
    )
    currency: CurrencyCode
    created_at: str = Field(
        min_length=1,
    )

class DocumentMetadata(StrictModel):
    relative_path: str = Field(
        min_length=1,
        max_length=500,
    )
    size_bytes: int = Field(
        ge=0,
    )


class DocumentContent(StrictModel):
    relative_path: str = Field(
        min_length=1,
        max_length=500,
    )
    content: str


class DocumentSearchMatch(StrictModel):
    relative_path: str = Field(
        min_length=1,
        max_length=500,
    )
    line_number: int = Field(
        gt=0,
    )
    excerpt: str = Field(
        min_length=1,
        max_length=500,
    )

class Shipment(StrictModel):
    order_id: int = Field(
        gt=0,
    )
    tracking_number: str = Field(
        min_length=3,
        max_length=100,
    )
    carrier: str = Field(
        min_length=1,
        max_length=100,
    )
    status: Literal[
        "label_created",
        "in_transit",
        "out_for_delivery",
        "delivered",
        "exception",
    ]
    estimated_delivery: str | None = Field(
        default=None,
        max_length=100,
    )


class DeliveryEvent(StrictModel):
    tracking_number: str = Field(
        min_length=3,
        max_length=100,
    )
    status: Literal[
        "label_created",
        "in_transit",
        "out_for_delivery",
        "delivered",
        "exception",
    ]
    description: str = Field(
        min_length=1,
        max_length=500,
    )
    occurred_at: str = Field(
        min_length=1,
        max_length=100,
    )
    location: str | None = Field(
        default=None,
        max_length=200,
    )
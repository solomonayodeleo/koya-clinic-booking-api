from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, field_validator

class Slot(BaseModel):
    id: str
    provider: str
    start: datetime
    end: datetime

    @field_validator("id", "provider", mode="before")
    @classmethod
    def check_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

class SlotWithAvailability(Slot):
    available: bool

class ResetRequest(BaseModel):
    slots: list[Slot]

class NewBooking(BaseModel):
    slot_id: str
    name: str
    email: EmailStr

    @field_validator("slot_id", mode="before")
    @classmethod
    def validate_slot_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("slot_id cannot be empty")
        return v.strip()

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("name cannot be empty")
        return v.strip()

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("email cannot be empty")
        return v.strip().lower()

class Booking(BaseModel):
    id: str
    slot_id: str
    name: str
    email: str
    status: Literal["confirmed", "cancelled"]
    created_at: datetime

class PaginatedBookings(BaseModel):
    bookings: list[Booking]
    next_cursor: str | None

class ErrorResponse(BaseModel):
    error: str

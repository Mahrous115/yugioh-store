from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ListingCreate(BaseModel):
    card_id: int
    card_name: str
    card_image: str
    price: float = Field(gt=0)
    stock: int = Field(ge=0)


class ListingUpdate(BaseModel):
    price: Optional[float] = Field(default=None, gt=0)
    stock: Optional[int] = Field(default=None, ge=0)


class Listing(BaseModel):
    id: str
    card_id: int
    card_name: str
    card_image: str
    price: float
    stock: int
    created_at: datetime

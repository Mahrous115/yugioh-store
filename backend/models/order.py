from pydantic import BaseModel, Field
from typing import List


class OrderCreate(BaseModel):
    # Each item: { card_id, card_name, card_image, price, quantity }
    items: List[dict]
    total: float = Field(gt=0)

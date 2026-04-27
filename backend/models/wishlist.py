from pydantic import BaseModel


class WishlistItemCreate(BaseModel):
    card_id: int
    card_name: str
    card_image: str

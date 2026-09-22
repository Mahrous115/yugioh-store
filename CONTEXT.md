# Duel Market

A multi-seller Yu-Gi-Oh! TCG marketplace, launching in Egypt and then MENA. Sellers list copies of cards for sale; buyers purchase them.

## Language

### Catalogue

**Card**:
A Yu-Gi-Oh! card as a game object, identified by its YGOPRODeck id, independent of any particular printing.
_Avoid_: Product, item

**Printing**:
A specific release of a Card, distinguished by set code, rarity and edition (e.g. `LOB-001` Ultra Rare 1st Edition). Not yet distinguished by Listings.
_Avoid_: Version, variant

### Selling

**Seller**:
A party that offers Listings on the marketplace. Today Duel Market itself is the only Seller.
_Avoid_: Vendor, merchant, shop

**Listing**:
A Seller's offer of copies of one Card in one Condition, with its own price and stock. A Seller has at most one Listing per Card and Condition, and a Listing's Card and Condition never change after it is created.
_Avoid_: Product, SKU, offer

**Condition**:
The physical state of an ungraded copy, on the fixed scale Near Mint (NM), Lightly Played (LP), Moderately Played (MP), Heavily Played (HP), Damaged (DMG), best to worst. Each level means what the Condition Guide says it means.
_Avoid_: Grade, quality, wear

**Condition Guide**:
Duel Market's own published definition of each Condition level. It is the reference when a buyer disputes a copy's Condition.
_Avoid_: Grading guide, condition chart

**Grade**:
A professional assessment of a copy by a grading service (PSA, BGS, CGC, or Duel Market's own future service). Reserved; not yet sold on the marketplace.
_Avoid_: Condition

### Buying

**Wishlist**:
The Cards a buyer wants, regardless of Condition or Seller.
_Avoid_: Favourites, watchlist

**Order Line**:
A record of one Listing bought within an order: the Card, its Condition, the price paid and the quantity, as they were at the moment of purchase. Later changes to the Listing never alter it. Order Lines from before Conditions existed have no Condition.
_Avoid_: Order item, cart line

# Listings are referenced by id, not by card

A Listing used to be identified by its Card (`UNIQUE (card_id)`), and the cart, the order request and `place_order` all located it by `card_id`. Adding Condition means one Card can have several Listings, and Sellers and Printings will multiply that further. We decided that everything which refers to a Listing (cart lines, order requests, `place_order`, order line items) carries the Listing's own id, and that "one Listing per Seller + Card (+ Printing) + Condition" is only a uniqueness constraint that nothing references. Adding Sellers or Printings then changes the constraint and adds columns, without changing how anything points at a Listing again.

## Considered Options

- **Reference by the combined fields** (`card_id` + `condition`, later + seller + printing). Rejected: every future addition would change the cart format, the request model, the `place_order` lookup and carts already saved in browsers.
- **No uniqueness at all** (Cardmarket-style duplicate listings). Rejected for Condition listings: one price per Condition per Seller keeps a Card's page legible. Because nothing references the natural key, dropping the constraint later is cheap.

## Consequences

- `place_order` finds each Listing by primary key, so it can never match more than one row. Migration 004's refusal to guess between several listings for a card becomes unnecessary for that lookup.
- Graded copies will not fit this uniqueness rule: each slab is its own item with its own certificate, so every one is a separate Listing with stock 1. Graded Listings need their own rule when they arrive.

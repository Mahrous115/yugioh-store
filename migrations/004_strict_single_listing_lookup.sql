-- Migration 004 — a second listing for one card must stop the sale, not be guessed at
-- Applied to the live project: NOT YET APPLIED
--
-- place_order resolves a cart line to a listing with
--
--     SELECT * INTO v_listing FROM public.listings WHERE card_id = v_card_id FOR UPDATE;
--
-- A non-STRICT SELECT INTO that matches several rows takes an arbitrary one. No error,
-- no warning, not even a NOTICE. Verified on this server (PostgreSQL 17): given two
-- matching rows the assignment silently picked the first. Applied to a real cart that
-- means locking one seller's row, pricing the sale from it, decrementing its stock and
-- attributing the money to that seller, with nothing anywhere to indicate a choice was
-- made at all.
--
-- Today that cannot happen: public.listings still carries listings_card_id_key,
-- UNIQUE (card_id), so a second row for a card cannot be inserted. This migration is
-- therefore inert on the current schema, and deliberately so -- it is the tripwire for
-- the day that constraint is dropped, which is exactly the day multi-seller listings
-- begin. The failure it guards against is silent and financial, and it would be
-- introduced by a schema change made somewhere else entirely, by someone who has no
-- reason to be reading this function.
--
-- A unique constraint is not the answer here and none is added. One row per card is
-- the shape the project intends to leave behind; enforcing it harder would be
-- enforcing the wrong thing, and would make the multi-seller change harder rather than
-- safer. The goal is that place_order refuses to guess, whatever the table allows.
--
-- Why the nested block, which is the part that is easy to get wrong:
--
-- STRICT raises on both edges, not just the one we want. TOO_MANY_ROWS (P0003) for two
-- or more rows is the point of the change. But NO_DATA_FOUND (P0002) for zero rows is
-- raised *before* control reaches the IF NOT FOUND below it, which turns that branch
-- into dead code. Confirmed on this server rather than assumed: with STRICT and zero
-- rows the block raised P0002 'query returned no rows' and never evaluated IF NOT
-- FOUND. Left alone, ordering an unlisted card would have stopped being a clean 400
-- 'Card N is not available for purchase' and become an unhandled exception surfacing
-- as a flat 500.
--
-- So the zero-row edge is caught and re-raised as the sentinel it always was, and the
-- IF NOT FOUND that can no longer fire is gone. TOO_MANY_ROWS is deliberately NOT
-- caught, and deliberately has no sentinel of its own: the anchored patterns in
-- _translate_place_order_error do not match 'query returned more than one row', so it
-- falls through to the flat 500 'Could not place order.' That is the correct answer.
-- The client did nothing wrong and there is nothing it can change about its request;
-- our data has outgrown our code, and the person who needs to know is on our side of
-- the wire, reading the log.
--
-- The nested BEGIN opens a subtransaction per cart line, which is a real but small
-- cost -- items[] is capped at 50 by the request model, and it buys the entire
-- sentinel contract back.

CREATE OR REPLACE FUNCTION public.place_order(
    p_user_id        uuid,
    p_items          jsonb,
    p_expected_total numeric DEFAULT NULL
)
RETURNS public.orders
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_item     jsonb;
    v_card_id  integer;
    v_qty      integer;
    v_listing  public.listings;
    v_total    numeric(10, 2) := 0;
    v_items    jsonb := '[]'::jsonb;
    v_order    public.orders;
BEGIN
    IF p_items IS NULL OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'EMPTY_ORDER';
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_card_id := (v_item ->> 'card_id')::integer;
        v_qty     := (v_item ->> 'quantity')::integer;

        IF v_qty IS NULL OR v_qty < 1 THEN
            RAISE EXCEPTION 'BAD_QUANTITY:%', v_card_id;
        END IF;

        -- FOR UPDATE is still the whole point: it blocks other buyers of this card
        -- until this transaction commits or rolls back. STRICT adds that the row it
        -- locks must be the only candidate.
        BEGIN
            SELECT * INTO STRICT v_listing
            FROM public.listings
            WHERE card_id = v_card_id
            FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                -- Replaces the IF NOT FOUND that STRICT made unreachable. Same
                -- sentinel, same 400, same message to the shopper.
                RAISE EXCEPTION 'NOT_LISTED:%', v_card_id;
            -- TOO_MANY_ROWS is intentionally not handled. See the header.
        END;

        IF v_listing.stock < v_qty THEN
            -- card_name last: names may contain the delimiter, the numbers may not.
            RAISE EXCEPTION 'INSUFFICIENT_STOCK:%:%:%',
                v_listing.stock, v_qty, v_listing.card_name;
        END IF;

        UPDATE public.listings
        SET stock = stock - v_qty
        WHERE id = v_listing.id;

        v_total := v_total + (v_listing.price * v_qty);

        -- Line items are rebuilt from the locked row, never from the request.
        v_items := v_items || jsonb_build_object(
            'card_id',    v_listing.card_id,
            'card_name',  v_listing.card_name,
            'card_image', v_listing.card_image,
            'price',      v_listing.price,
            'quantity',   v_qty
        );
    END LOOP;

    -- Checked before the INSERT, but after the decrements -- raising here rolls those
    -- back with everything else, so a refused order never costs stock.
    IF p_expected_total IS NOT NULL
       AND round(p_expected_total, 2) <> round(v_total, 2) THEN
        RAISE EXCEPTION 'TOTAL_MISMATCH:%:%', v_total, round(p_expected_total, 2);
    END IF;

    INSERT INTO public.orders (user_id, items, total)
    VALUES (p_user_id, v_items, v_total)
    RETURNING * INTO v_order;

    RETURN v_order;
END;
$$;

-- Re-asserted rather than assumed. CREATE OR REPLACE keeps the privileges of a
-- function that already exists, so on the live project these are a no-op -- but on a
-- database where 003 was never applied, CREATE would grant EXECUTE to PUBLIC by
-- default and hand the browser a way to create orders without passing through the
-- API's auth and rate limiting. That is the H1 hole reopened through a different door,
-- and it would arrive as a side effect of a migration about something else.
REVOKE ALL ON FUNCTION public.place_order(uuid, jsonb, numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.place_order(uuid, jsonb, numeric) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.place_order(uuid, jsonb, numeric) TO service_role;

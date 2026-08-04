-- Migration 003 — make stock real and decrement it atomically (AUDIT.md finding L8)
-- Applied to the live project: 2026-08-04
--
-- listings.stock was display-only: shown in the UI and used to disable the
-- Add-to-Cart button, but never decremented by a purchase. Orders were also written
-- with no transaction spanning a stock check, so bolting a check onto the Python
-- side would still have raced -- four concurrent buyers all read stock=2 before any
-- of them wrote, and all four orders succeeded (demonstrated in
-- backend/tests/test_l8_stock.py::test_concurrent_buyers_cannot_oversell).
--
-- PostgREST cannot span statements in one transaction, so the whole operation moves
-- into a function. A plpgsql function body is a single transaction: SELECT ... FOR
-- UPDATE serialises concurrent buyers on the same listing row, and any RAISE rolls
-- back every stock change made earlier in the call.
--
-- Pricing stays here too rather than in Python (finding C2): the price used for the
-- total is read from the same locked row that the stock came from, so a concurrent
-- repricing cannot land between the quote and the charge.

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

        -- FOR UPDATE is the whole point: it blocks other buyers of this card until
        -- this transaction commits or rolls back.
        SELECT * INTO v_listing
        FROM public.listings
        WHERE card_id = v_card_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'NOT_LISTED:%', v_card_id;
        END IF;

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

-- Backend only. Granting this to anon/authenticated would hand the browser a way to
-- create orders without passing through the API's auth and rate limiting -- the same
-- shape of hole as H1, reopened through a different door.
REVOKE ALL ON FUNCTION public.place_order(uuid, jsonb, numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.place_order(uuid, jsonb, numeric) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.place_order(uuid, jsonb, numeric) TO service_role;

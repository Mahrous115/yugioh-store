import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { useListings } from '../context/ListingsContext'
import { createOrder } from '../services/api'
import CartItem from '../components/CartItem'

/**
 * Turn a failed checkout into something a shopper can act on.
 *
 * The server distinguishes these deliberately, so the cart should too:
 *   409  a line exceeds available stock — `detail` names the card
 *   400  the total disagrees with the catalogue (prices moved since adding)
 *   429  too many orders too quickly
 */
function describeCheckoutError(e) {
  if (e.status === 409) {
    return {
      tone: 'error',
      // The backend message already names the card and both quantities.
      text: e.message,
      hint: 'Lower the quantity or remove that card, then try again.',
    }
  }
  if (e.status === 400) {
    return {
      tone: 'error',
      text: 'Prices changed while this cart was open, so the order was not placed.',
      hint: 'Your cart has been updated to the current prices — check the new total and try again.',
    }
  }
  if (e.status === 429) {
    const wait = Number.isFinite(e.retryAfter) && e.retryAfter > 0
      ? `about ${e.retryAfter} second${e.retryAfter === 1 ? '' : 's'}`
      : 'a moment'
    return {
      tone: 'error',
      text: `Too many orders placed in a short time. Please wait ${wait} and try again.`,
      hint: 'Nothing was charged and your cart is unchanged.',
    }
  }
  if (e.status === 401) {
    return {
      tone: 'error',
      text: 'Your session has expired.',
      hint: 'Log in again to place this order.',
    }
  }
  return { tone: 'error', text: e.message || 'Could not place the order.', hint: null }
}

export default function Cart() {
  const { items, total, clearCart, syncPrices } = useCart()
  const { user }    = useAuth()
  const { byCardId, stockOf, refresh } = useListings()
  const navigate    = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  // Lines the shop can no longer fill. Recomputed on every render from the shared
  // listings, so a refresh after a failed checkout immediately shows the problem
  // against the offending row rather than only in the banner.
  const overStock = items.filter(i => {
    const available = stockOf(i.card_id)
    return available !== null && i.quantity > available
  })

  async function handleCheckout() {
    if (!user) { navigate('/login', { state: { from: '/cart' } }); return }

    setLoading(true)
    setError(null)
    try {
      // card_name/card_image/price are ignored by the server, which rebuilds each
      // line from the catalogue. Sent anyway so the payload stays self-describing
      // in the network tab; `total` is what the server checks against.
      const order = await createOrder({
        items: items.map(({ card_id, card_name, card_image, price, quantity }) => ({
          card_id, card_name, card_image, price, quantity,
        })),
        total,
      })
      clearCart()
      await refresh()   // stock just moved
      navigate('/checkout/confirmation', { state: { order } })
    } catch (e) {
      setError(describeCheckoutError(e))

      // Both of these mean the cart is out of date with the shop. Re-read the
      // listings so the page stops showing the numbers that just got rejected.
      if (e.status === 409 || e.status === 400) {
        const fresh = await refresh()
        // On a price mismatch, re-pricing the cart is the fix. Without it the
        // shopper can only retry the same rejected total forever.
        if (fresh && e.status === 400) {
          syncPrices(new Map(fresh.map(l => [l.card_id, l])))
        }
      }
    } finally {
      setLoading(false)
    }
  }

  if (items.length === 0) {
    return (
      <div className="page">
        <div className="empty-state">
          <span className="empty-state__icon">🛒</span>
          <h2>Your cart is empty</h2>
          <p>Browse the catalog and add some cards!</p>
          <Link to="/catalog" className="btn btn--gold">Browse Catalog</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <h1 className="page__title">Shopping Cart</h1>

      <div className="cart-layout">
        {/* Items list */}
        <div className="cart-items">
          {items.map(item => (
            <CartItem
              key={item.card_id}
              item={item}
              available={stockOf(item.card_id)}
            />
          ))}
        </div>

        {/* Order summary */}
        <aside className="order-summary">
          <h2 className="order-summary__title">Order Summary</h2>
          <div className="order-summary__row">
            <span>Items ({items.reduce((s, i) => s + i.quantity, 0)})</span>
            <span>${total.toFixed(2)}</span>
          </div>
          <div className="order-summary__row">
            <span>Shipping</span>
            <span className="text-gold">FREE</span>
          </div>
          <div className="order-summary__divider" />
          <div className="order-summary__row order-summary__total">
            <span>Total</span>
            <span>${total.toFixed(2)}</span>
          </div>

          {error && (
            <div className={`alert alert--${error.tone}`}>
              <p style={{ margin: 0 }}>{error.text}</p>
              {error.hint && (
                <p style={{ margin: '0.35rem 0 0', opacity: 0.85, fontSize: '0.85em' }}>
                  {error.hint}
                </p>
              )}
            </div>
          )}

          {!error && overStock.length > 0 && (
            <div className="alert alert--error">
              <p style={{ margin: 0 }}>
                {overStock.length === 1
                  ? `Only ${stockOf(overStock[0].card_id)} left of "${overStock[0].card_name}".`
                  : `${overStock.length} cards in this cart exceed available stock.`}
              </p>
              <p style={{ margin: '0.35rem 0 0', opacity: 0.85, fontSize: '0.85em' }}>
                Adjust the quantities before checking out.
              </p>
            </div>
          )}

          <button
            className="btn btn--gold btn--lg btn--full"
            onClick={handleCheckout}
            disabled={loading || overStock.length > 0}
          >
            {loading
              ? 'Placing order…'
              : overStock.length > 0
                ? 'Adjust quantities to continue'
                : user ? 'Place Order' : 'Log in to Checkout'}
          </button>

          <Link to="/catalog" className="btn btn--ghost btn--full" style={{ marginTop: 8 }}>
            Continue Shopping
          </Link>
        </aside>
      </div>
    </div>
  )
}

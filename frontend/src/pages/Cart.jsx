import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { createOrder } from '../services/api'
import CartItem from '../components/CartItem'

export default function Cart() {
  const { items, total, clearCart } = useCart()
  const { user }    = useAuth()
  const navigate    = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  async function handleCheckout() {
    if (!user) { navigate('/login', { state: { from: '/cart' } }); return }

    setLoading(true)
    setError('')
    try {
      const order = await createOrder({
        items: items.map(({ card_id, card_name, card_image, price, quantity }) => ({
          card_id, card_name, card_image, price, quantity,
        })),
        total,
      })
      clearCart()
      navigate('/checkout/confirmation', { state: { order } })
    } catch (e) {
      setError(e.message)
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
          {items.map(item => <CartItem key={item.card_id} item={item} />)}
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

          {error && <div className="alert alert--error">{error}</div>}

          <button
            className="btn btn--gold btn--lg btn--full"
            onClick={handleCheckout}
            disabled={loading}
          >
            {loading ? 'Placing order…' : user ? 'Place Order' : 'Log in to Checkout'}
          </button>

          <Link to="/catalog" className="btn btn--ghost btn--full" style={{ marginTop: 8 }}>
            Continue Shopping
          </Link>
        </aside>
      </div>
    </div>
  )
}

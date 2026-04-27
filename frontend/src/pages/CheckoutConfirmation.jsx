import { useLocation, Link, Navigate } from 'react-router-dom'

export default function CheckoutConfirmation() {
  const { state } = useLocation()
  const order     = state?.order

  // If user navigates here directly without an order, redirect to catalog
  if (!order) return <Navigate to="/catalog" replace />

  const date = new Date(order.created_at).toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  })

  return (
    <div className="page confirmation">
      <div className="confirmation__card">
        <div className="confirmation__icon">✓</div>
        <h1 className="confirmation__title">Order Confirmed!</h1>
        <p className="confirmation__sub">Thank you for your purchase on Duel Market.</p>

        <div className="confirmation__meta">
          <span className="confirmation__id">Order #{order.id.slice(0, 8).toUpperCase()}</span>
          <span className="confirmation__date">{date}</span>
        </div>

        {/* Item list */}
        <div className="confirmation__items">
          {order.items.map((item, i) => (
            <div key={i} className="confirmation__item">
              <img src={item.card_image} alt={item.card_name} className="confirmation__item-img" />
              <span className="confirmation__item-name">{item.card_name}</span>
              <span className="confirmation__item-qty">× {item.quantity}</span>
              <span className="confirmation__item-price">
                ${(item.price * item.quantity).toFixed(2)}
              </span>
            </div>
          ))}
        </div>

        <div className="confirmation__total">
          Total paid: <strong>${order.total.toFixed(2)}</strong>
        </div>

        <div className="confirmation__actions">
          <Link to="/profile" className="btn btn--gold">View My Orders</Link>
          <Link to="/catalog" className="btn btn--ghost">Continue Shopping</Link>
        </div>
      </div>
    </div>
  )
}

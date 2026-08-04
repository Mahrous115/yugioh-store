import { useCart } from '../context/CartContext'

/**
 * @param available  units the shop currently has, or null when the card is no
 *                   longer listed at all. Undefined while listings are loading.
 */
export default function CartItem({ item, available }) {
  const { setQuantity, removeFromCart } = useCart()

  const knownStock = typeof available === 'number'
  const unlisted   = available === null
  const overStock  = knownStock && item.quantity > available
  const atMax      = knownStock && item.quantity >= available

  return (
    <div className="cart-item">
      <img src={item.card_image} alt={item.card_name} className="cart-item__img" />

      <div className="cart-item__info">
        <p className="cart-item__name">{item.card_name}</p>
        <p className="cart-item__price">${item.price.toFixed(2)} each</p>

        {unlisted && (
          <p className="cart-item__stock cart-item__stock--warn">
            No longer sold — remove to check out
          </p>
        )}
        {overStock && (
          <p className="cart-item__stock cart-item__stock--warn">
            Only {available} left {available === 0 ? '' : `— reduce to ${available}`}
          </p>
        )}
        {knownStock && !overStock && available <= 3 && available > 0 && (
          <p className="cart-item__stock">Only {available} left in stock</p>
        )}
      </div>

      <div className="cart-item__qty">
        <button
          className="qty-btn"
          onClick={() => setQuantity(item.card_id, item.quantity - 1)}
          aria-label="Decrease quantity"
        >−</button>
        <span className="qty-value">{item.quantity}</span>
        <button
          className="qty-btn"
          onClick={() => setQuantity(item.card_id, item.quantity + 1)}
          // Stop the shopper walking into a 409 the server would only reject
          disabled={atMax}
          title={atMax ? `Only ${available} in stock` : undefined}
          aria-label="Increase quantity"
        >+</button>
      </div>

      <p className="cart-item__subtotal">${(item.price * item.quantity).toFixed(2)}</p>

      <button
        className="cart-item__remove"
        onClick={() => removeFromCart(item.card_id)}
        aria-label="Remove from cart"
      >✕</button>
    </div>
  )
}

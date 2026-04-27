import { useCart } from '../context/CartContext'

export default function CartItem({ item }) {
  const { setQuantity, removeFromCart } = useCart()

  return (
    <div className="cart-item">
      <img src={item.card_image} alt={item.card_name} className="cart-item__img" />

      <div className="cart-item__info">
        <p className="cart-item__name">{item.card_name}</p>
        <p className="cart-item__price">${item.price.toFixed(2)} each</p>
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

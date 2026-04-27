import { Link } from 'react-router-dom'
import { useWishlist } from '../hooks/useWishlist'
import LoadingSpinner from '../components/LoadingSpinner'

export default function Wishlist() {
  const { items, loading, toggle } = useWishlist()

  if (loading) return <LoadingSpinner size={56} />

  return (
    <div className="page">
      <h1 className="page__title">My Wishlist</h1>

      {items.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon">♡</span>
          <h2>Your wishlist is empty</h2>
          <p>Click the heart on any card to save it here.</p>
          <Link to="/catalog" className="btn btn--gold">Browse Catalog</Link>
        </div>
      ) : (
        <div className="wishlist-grid">
          {items.map(item => (
            <div key={item.card_id} className="wishlist-item">
              <Link to={`/cards/${item.card_id}`}>
                <img src={item.card_image} alt={item.card_name} className="wishlist-item__img" />
                <p className="wishlist-item__name">{item.card_name}</p>
              </Link>
              <button
                className="btn btn--ghost btn--sm wishlist-item__remove"
                onClick={() => toggle({ id: item.card_id, name: item.card_name, card_images: [{ image_url: item.card_image }] })}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

import { Link } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { useWishlist } from '../hooks/useWishlist'

/**
 * Compact card tile used in the catalog grid.
 * Accepts a YGOPRODeck card object plus an optional `listing` from our backend.
 */
export default function CardCard({ card, listing }) {
  const { user }         = useAuth()
  const { addToCart }    = useCart()
  const { isWishlisted, toggle } = useWishlist()

  const wishlisted = isWishlisted(card.id)
  const img        = card.card_images?.[0]?.image_url_small ?? card.card_images?.[0]?.image_url

  function handleAddToCart(e) {
    e.preventDefault()
    addToCart({
      card_id:    card.id,
      card_name:  card.name,
      card_image: card.card_images[0].image_url,
      price:      listing.price,
    })
  }

  function handleWishlist(e) {
    e.preventDefault()
    toggle(card)
  }

  return (
    <Link to={`/cards/${card.id}`} className="card-tile">
      <div className="card-tile__img-wrap">
        <img src={img} alt={card.name} className="card-tile__img" loading="lazy" />
        {user && (
          <button
            className={`card-tile__wish ${wishlisted ? 'card-tile__wish--active' : ''}`}
            onClick={handleWishlist}
            title={wishlisted ? 'Remove from wishlist' : 'Add to wishlist'}
          >
            ♥
          </button>
        )}
      </div>

      <div className="card-tile__body">
        <p className="card-tile__name">{card.name}</p>
        <p className="card-tile__type">{card.type}</p>

        {listing ? (
          <>
            <p className="card-tile__price">${listing.price.toFixed(2)}</p>
            <button
              className="btn btn--gold btn--sm card-tile__cart"
              onClick={handleAddToCart}
              disabled={listing.stock === 0}
            >
              {listing.stock === 0 ? 'Out of Stock' : 'Add to Cart'}
            </button>
          </>
        ) : (
          <p className="card-tile__unlisted">Not listed</p>
        )}
      </div>
    </Link>
  )
}

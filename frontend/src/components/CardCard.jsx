import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { useWishlist } from '../hooks/useWishlist'
import Icon from './Icon'

/**
 * Compact card tile used in the catalog grid.
 * Accepts a YGOPRODeck card object plus an optional `listing` from our backend.
 */
export default function CardCard({ card, listing }) {
  const { user }         = useAuth()
  const { addToCart }    = useCart()
  const { isWishlisted, toggle } = useWishlist()
  const navigate = useNavigate()
  const location = useLocation()

  // Brief "Added" confirmation on the button itself. The navbar badge also
  // reacts, but that is easy to miss from the bottom of a long grid, so the
  // control you actually clicked acknowledges the click too.
  const [added, setAdded] = useState(false)
  const addedTimer = useRef(null)
  useEffect(() => () => clearTimeout(addedTimer.current), [])

  const wishlisted = isWishlisted(card.id)
  const img        = card.card_images?.[0]?.image_url_small ?? card.card_images?.[0]?.image_url

  function handleAddToCart(e) {
    // The whole tile is a <Link> to the card page — without this, adding to the
    // cart would also navigate away from the grid.
    e.preventDefault()
    e.stopPropagation()

    // The cart is a signed-in feature. Send guests to log in and bring them
    // back here afterwards rather than filling a cart they cannot check out.
    if (!user) {
      navigate('/login', { state: { from: location.pathname + location.search } })
      return
    }

    addToCart({
      card_id:    card.id,
      card_name:  card.name,
      card_image: card.card_images[0].image_url,
      price:      listing.price,
    })

    setAdded(true)
    clearTimeout(addedTimer.current)
    addedTimer.current = setTimeout(() => setAdded(false), 1600)
  }

  function handleWishlist(e) {
    e.preventDefault()
    e.stopPropagation()
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
            aria-label={wishlisted ? 'Remove from wishlist' : 'Add to wishlist'}
          >
            <Icon name="heart" size={15} filled={wishlisted} />
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
              className={`btn btn--gold btn--sm card-tile__cart${added ? ' btn--added' : ''}`}
              onClick={handleAddToCart}
              disabled={listing.stock === 0}
            >
              {listing.stock === 0
                ? 'Out of Stock'
                : added
                  ? <><Icon name="check" size={14} /> Added</>
                  : user ? 'Add to Cart' : 'Log in to Buy'}
            </button>
          </>
        ) : (
          <p className="card-tile__unlisted">Not listed</p>
        )}
      </div>
    </Link>
  )
}

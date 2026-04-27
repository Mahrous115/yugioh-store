import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getCardById } from '../services/ygoprodeck'
import { getListings } from '../services/api'
import { useCart } from '../context/CartContext'
import { useAuth } from '../context/AuthContext'
import { useWishlist } from '../hooks/useWishlist'
import LoadingSpinner from '../components/LoadingSpinner'

export default function CardDetail() {
  const { id }    = useParams()
  const { user }  = useAuth()
  const { addToCart }          = useCart()
  const { isWishlisted, toggle } = useWishlist()

  const [card,    setCard]    = useState(null)
  const [listing, setListing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [added,   setAdded]   = useState(false)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [cardData, listings] = await Promise.all([
          getCardById(id),
          getListings(),
        ])
        setCard(cardData)
        setListing(listings.find(l => l.card_id === cardData.id) ?? null)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id])

  function handleAddToCart() {
    addToCart({
      card_id:    card.id,
      card_name:  card.name,
      card_image: card.card_images[0].image_url,
      price:      listing.price,
    })
    setAdded(true)
    setTimeout(() => setAdded(false), 2000)
  }

  if (loading) return <LoadingSpinner size={60} />
  if (error)   return <div className="page"><div className="alert alert--error">{error}</div></div>
  if (!card)   return null

  const prices   = card.card_prices?.[0] ?? {}
  const wishlisted = isWishlisted(card.id)

  return (
    <div className="page card-detail">
      {/* Breadcrumb */}
      <nav className="breadcrumb">
        <Link to="/">Home</Link> / <Link to="/catalog">Catalog</Link> / <span>{card.name}</span>
      </nav>

      <div className="card-detail__layout">
        {/* Card image */}
        <div className="card-detail__img-col">
          <img
            src={card.card_images[0].image_url}
            alt={card.name}
            className="card-detail__img"
          />
          {user && (
            <button
              className={`btn btn--full ${wishlisted ? 'btn--outline' : 'btn--ghost'}`}
              onClick={() => toggle(card)}
            >
              {wishlisted ? '♥ Remove from Wishlist' : '♡ Add to Wishlist'}
            </button>
          )}
        </div>

        {/* Card info */}
        <div className="card-detail__info">
          <h1 className="card-detail__name">{card.name}</h1>
          <p className="card-detail__type">{card.type}</p>

          {/* Stats */}
          <div className="card-detail__stats">
            {card.level     != null && <Stat label="Level"     value={card.level} />}
            {card.attribute        && <Stat label="Attribute"  value={card.attribute} />}
            {card.race             && <Stat label="Race"       value={card.race} />}
            {card.atk       != null && <Stat label="ATK"       value={card.atk} />}
            {card.def       != null && <Stat label="DEF"       value={card.def} />}
            {card.linkval   != null && <Stat label="Link"      value={card.linkval} />}
          </div>

          {/* Description */}
          <p className="card-detail__desc">{card.desc}</p>

          {/* Market prices (read-only info from YGOPRODeck) */}
          <div className="card-detail__prices">
            <h3 className="card-detail__prices-title">Market Prices</h3>
            <div className="price-grid">
              {prices.cardmarket_price   && <PriceRow source="Cardmarket"  value={prices.cardmarket_price} />}
              {prices.tcgplayer_price    && <PriceRow source="TCGPlayer"   value={prices.tcgplayer_price} />}
              {prices.ebay_price         && <PriceRow source="eBay"        value={prices.ebay_price} />}
              {prices.amazon_price       && <PriceRow source="Amazon"      value={prices.amazon_price} />}
            </div>
          </div>

          {/* Our listing */}
          {listing ? (
            <div className="card-detail__listing">
              <div className="card-detail__listing-price">
                <span className="listing-label">Our Price</span>
                <span className="listing-value">${listing.price.toFixed(2)}</span>
              </div>
              <p className="listing-stock">
                {listing.stock > 0 ? `${listing.stock} in stock` : 'Out of stock'}
              </p>
              <button
                className="btn btn--gold btn--lg btn--full"
                onClick={handleAddToCart}
                disabled={listing.stock === 0}
              >
                {added ? '✓ Added to Cart!' : 'Add to Cart'}
              </button>
            </div>
          ) : (
            <p className="card-detail__unlisted">This card is not currently listed for sale.</p>
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
    </div>
  )
}

function PriceRow({ source, value }) {
  return (
    <div className="price-row">
      <span className="price-row__source">{source}</span>
      <span className="price-row__value">${parseFloat(value).toFixed(2)}</span>
    </div>
  )
}

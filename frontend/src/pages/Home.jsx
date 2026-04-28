import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { searchCards } from '../services/ygoprodeck'
import { getListings } from '../services/api'
import CardGrid from '../components/CardGrid'
import { useAuth } from '../context/AuthContext'

const FEATURED_SEARCH = 'dragon'

export default function Home() {
  const { user } = useAuth()
  const [cards,      setCards]      = useState([])
  const [listingMap, setListingMap] = useState(new Map())
  const [loading,    setLoading]    = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [cardRes, listings] = await Promise.all([
          searchCards({ fname: FEATURED_SEARCH, num: 8 }),
          getListings(),
        ])
        setCards(cardRes.data)
        setListingMap(new Map(listings.map(l => [l.card_id, l])))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div>
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="hero">
        <div className="hero__content">
          <p className="hero__eyebrow">The Ultimate Card Marketplace</p>
          <h1 className="hero__title">Duel Market</h1>
          <p className="hero__subtitle">
            Browse thousands of Yu-Gi-Oh! cards, track your wishlist, and shop
            custom listings — all in one dark, golden arena.
          </p>
          <div className="hero__cta">
            <Link to="/catalog" className="btn btn--gold btn--lg">Browse Catalog</Link>
            {!user && (
              <Link to="/register" className="btn btn--outline btn--lg">Create Account</Link>
            )}
          </div>
        </div>
        <div className="hero__decoration" aria-hidden="true">★</div>
      </section>

      {/* ── Feature pillars ──────────────────────────────────── */}
      <section className="features">
        <div className="feature">
          <span className="feature__icon">🃏</span>
          <h3>12 000+ Cards</h3>
          <p>Full YGOPRODeck catalogue with real artwork, stats, and market prices.</p>
        </div>
        <div className="feature">
          <span className="feature__icon">♥</span>
          <h3>Personal Wishlist</h3>
          <p>Save any card to your wishlist and access it from any device.</p>
        </div>
        <div className="feature">
          <span className="feature__icon">🛒</span>
          <h3>Custom Listings</h3>
          <p>Admin-curated listings with hand-picked prices and live stock levels.</p>
        </div>
      </section>

      {/* ── Featured cards ────────────────────────────────────── */}
      <section className="section">
        <div className="section__header">
          <h2 className="section__title">Featured Dragons</h2>
          <Link to="/catalog" className="btn btn--ghost btn--sm">View all →</Link>
        </div>
        <CardGrid cards={cards} listingMap={listingMap} loading={loading} />
      </section>
    </div>
  )
}

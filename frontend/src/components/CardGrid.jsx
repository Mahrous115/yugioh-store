import CardCard from './CardCard'
import LoadingSpinner from './LoadingSpinner'

/**
 * Responsive grid of CardCard tiles.
 * `listingMap` is a Map<card_id, listing> built by the parent page
 * so each CardCard knows if the card has an active listing.
 */
export default function CardGrid({ cards, listingMap = new Map(), loading }) {
  if (loading) return <LoadingSpinner size={56} />

  if (!cards.length) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">🃏</span>
        <p>No cards found. Try a different search.</p>
      </div>
    )
  }

  return (
    <div className="card-grid">
      {cards.map(card => (
        <CardCard key={card.id} card={card} listing={listingMap.get(card.id)} />
      ))}
    </div>
  )
}

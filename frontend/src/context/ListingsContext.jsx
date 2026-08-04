/**
 * ListingsContext — one shared, refreshable copy of the shop's listings.
 *
 * Catalog used to fetch these once with the comment "they don't change during a
 * session". That stopped being true when purchases started decrementing stock
 * (backend migration 003): after checking out, every mounted view was showing the
 * stock level from before the order.
 *
 * Holding them here means a purchase can call refresh() once and every view that
 * renders stock or price updates together.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getListings } from '../services/api'

const ListingsContext = createContext({})

export function ListingsProvider({ children }) {
  const [listings, setListings] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)

  /**
   * Re-read the listings.
   *
   * Returns the fresh rows as well as storing them: a caller that refreshes and
   * then acts on the result cannot use the context value from its own closure,
   * which is still the pre-refresh render's copy.
   */
  const refresh = useCallback(async () => {
    try {
      const fresh = await getListings()
      setListings(fresh)
      setError(null)
      return fresh
    } catch (e) {
      // Keep whatever we already have rather than blanking the shop on a blip.
      setError(e.message)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const byCardId = useMemo(
    () => new Map(listings.map(l => [l.card_id, l])),
    [listings],
  )

  /** Stock currently available for a card, or null if it is not listed at all. */
  const stockOf = useCallback(
    card_id => byCardId.get(card_id)?.stock ?? null,
    [byCardId],
  )

  return (
    <ListingsContext.Provider value={{ listings, byCardId, stockOf, loading, error, refresh }}>
      {children}
    </ListingsContext.Provider>
  )
}

export const useListings = () => useContext(ListingsContext)

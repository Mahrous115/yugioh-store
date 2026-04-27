/**
 * WishlistContext — provides wishlist state globally so that every CardCard
 * in the catalog reads from one shared state instead of each making its own
 * API call.  WishlistProvider must be nested inside AuthProvider.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { getWishlist, addToWishlist, removeFromWishlist } from '../services/api'
import { useAuth } from './AuthContext'

const WishlistContext = createContext({})

export function WishlistProvider({ children }) {
  const { user }  = useAuth()
  const [items,   setItems]   = useState([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!user) { setItems([]); return }
    setLoading(true)
    try { setItems(await getWishlist()) }
    catch { /* silently ignore */ }
    finally { setLoading(false) }
  }, [user])

  useEffect(() => { load() }, [load])

  const isWishlisted = card_id => items.some(i => i.card_id === card_id)

  async function toggle(card) {
    // card must have: { id, name, card_images: [{ image_url }] }
    if (isWishlisted(card.id)) {
      setItems(prev => prev.filter(i => i.card_id !== card.id))
      try { await removeFromWishlist(card.id) }
      catch { load() }
    } else {
      const item = {
        card_id:    card.id,
        card_name:  card.name,
        card_image: card.card_images[0].image_url,
      }
      setItems(prev => [...prev, item])
      try { await addToWishlist(item) }
      catch { load() }
    }
  }

  return (
    <WishlistContext.Provider value={{ items, loading, isWishlisted, toggle, reload: load }}>
      {children}
    </WishlistContext.Provider>
  )
}

export const useWishlistContext = () => useContext(WishlistContext)

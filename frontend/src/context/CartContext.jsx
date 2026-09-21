import { createContext, useContext, useEffect, useReducer } from 'react'

const CartContext  = createContext({})
const STORAGE_KEY  = 'yugioh_cart'

function reducer(state, action) {
  switch (action.type) {
    // Rehydrating is not an add. It deliberately leaves `lastAdded` alone so a
    // page load does not fire the cart's "just added" animation for items that
    // have been sitting in localStorage since a previous visit.
    case 'LOAD':
      return { ...state, items: action.items }

    case 'ADD': {
      // A fresh object every time, even for a card already in the cart: it is
      // the signal the navbar badge animates off, and re-adding the same card
      // has to re-fire it.
      const lastAdded = { card_id: action.item.card_id, at: Date.now() }
      const exists = state.items.find(i => i.card_id === action.item.card_id)
      if (exists) {
        return {
          lastAdded,
          items: state.items.map(i =>
            i.card_id === action.item.card_id ? { ...i, quantity: i.quantity + 1 } : i
          ),
        }
      }
      return { lastAdded, items: [...state.items, { ...action.item, quantity: 1 }] }
    }

    case 'REMOVE':
      return { ...state, items: state.items.filter(i => i.card_id !== action.card_id) }

    case 'SET_QTY':
      if (action.quantity <= 0)
        return { ...state, items: state.items.filter(i => i.card_id !== action.card_id) }
      return {
        ...state,
        items: state.items.map(i =>
          i.card_id === action.card_id ? { ...i, quantity: action.quantity } : i
        ),
      }

    // Re-price the cart from the shop's current listings. Cart lines cache the
    // price from when they were added, and the server rejects an order whose
    // total disagrees with the catalogue — so after that rejection the cart has
    // to be brought back in line before retrying is anything but a loop.
    case 'SYNC_PRICES':
      return {
        ...state,
        items: state.items.map(i => {
          const listing = action.byCardId.get(i.card_id)
          return listing ? { ...i, price: listing.price } : i
        }),
      }

    case 'CLEAR':
      return { ...state, items: [] }

    default:
      return state
  }
}

export function CartProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, { items: [], lastAdded: null })

  // Rehydrate from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) dispatch({ type: 'LOAD', items: JSON.parse(saved) })
    } catch {
      // Ignore corrupt storage
    }
  }, [])

  // Persist to localStorage whenever the cart changes
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.items))
  }, [state.items])

  const addToCart     = item        => dispatch({ type: 'ADD',     item })
  const removeFromCart = card_id   => dispatch({ type: 'REMOVE',  card_id })
  const setQuantity   = (card_id, quantity) => dispatch({ type: 'SET_QTY', card_id, quantity })
  const clearCart     = ()          => dispatch({ type: 'CLEAR' })
  const syncPrices    = byCardId    => dispatch({ type: 'SYNC_PRICES', byCardId })

  const itemCount = state.items.reduce((s, i) => s + i.quantity, 0)
  const total     = state.items.reduce((s, i) => s + i.price * i.quantity, 0)

  return (
    <CartContext.Provider value={{
      items: state.items,
      lastAdded: state.lastAdded,
      itemCount,
      total,
      addToCart,
      removeFromCart,
      setQuantity,
      clearCart,
      syncPrices,
    }}>
      {children}
    </CartContext.Provider>
  )
}

export const useCart = () => useContext(CartContext)

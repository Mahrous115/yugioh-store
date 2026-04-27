import { createContext, useContext, useEffect, useReducer } from 'react'

const CartContext  = createContext({})
const STORAGE_KEY  = 'yugioh_cart'

function reducer(state, action) {
  switch (action.type) {
    case 'LOAD':
      return { items: action.items }

    case 'ADD': {
      const exists = state.items.find(i => i.card_id === action.item.card_id)
      if (exists) {
        return {
          items: state.items.map(i =>
            i.card_id === action.item.card_id ? { ...i, quantity: i.quantity + 1 } : i
          ),
        }
      }
      return { items: [...state.items, { ...action.item, quantity: 1 }] }
    }

    case 'REMOVE':
      return { items: state.items.filter(i => i.card_id !== action.card_id) }

    case 'SET_QTY':
      if (action.quantity <= 0)
        return { items: state.items.filter(i => i.card_id !== action.card_id) }
      return {
        items: state.items.map(i =>
          i.card_id === action.card_id ? { ...i, quantity: action.quantity } : i
        ),
      }

    case 'CLEAR':
      return { items: [] }

    default:
      return state
  }
}

export function CartProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, { items: [] })

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

  const itemCount = state.items.reduce((s, i) => s + i.quantity, 0)
  const total     = state.items.reduce((s, i) => s + i.price * i.quantity, 0)

  return (
    <CartContext.Provider value={{
      items: state.items,
      itemCount,
      total,
      addToCart,
      removeFromCart,
      setQuantity,
      clearCart,
    }}>
      {children}
    </CartContext.Provider>
  )
}

export const useCart = () => useContext(CartContext)

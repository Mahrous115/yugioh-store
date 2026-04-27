import { useState, useEffect, useCallback } from 'react'
import { getOrders } from '../services/api'
import { useAuth } from '../context/AuthContext'

/** Fetches and caches the authenticated user's order history. */
export function useOrders() {
  const { user } = useAuth()
  const [orders,  setOrders]  = useState([])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const load = useCallback(async () => {
    if (!user) { setOrders([]); return }
    setLoading(true)
    try {
      const data = await getOrders()
      setOrders(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => { load() }, [load])

  return { orders, loading, error, reload: load }
}

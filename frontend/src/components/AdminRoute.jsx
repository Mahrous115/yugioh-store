import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from './LoadingSpinner'

/** Requires authentication AND role='admin'; otherwise redirects away. */
export default function AdminRoute({ children }) {
  const { user, profile, loading } = useAuth()
  if (loading)              return <LoadingSpinner />
  if (!user)                return <Navigate to="/login"  replace />
  if (profile?.role !== 'admin') return <Navigate to="/"  replace />
  return children
}

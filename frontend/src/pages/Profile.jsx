import { useAuth } from '../context/AuthContext'
import { useOrders } from '../hooks/useOrders'
import LoadingSpinner from '../components/LoadingSpinner'

export default function Profile() {
  const { user, profile }   = useAuth()
  const { orders, loading } = useOrders()

  return (
    <div className="page">
      <h1 className="page__title">My Profile</h1>

      {/* User info card */}
      <div className="profile-card">
        <div className="profile-card__avatar">
          {user?.email?.[0]?.toUpperCase()}
        </div>
        <div>
          <p className="profile-card__email">{user?.email}</p>
          <p className="profile-card__role">
            Role: <span className={`badge badge--${profile?.role}`}>{profile?.role ?? 'user'}</span>
          </p>
          <p className="profile-card__since">
            Member since {new Date(user?.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>

      {/* Order history */}
      <h2 className="section-title">Order History</h2>

      {loading ? (
        <LoadingSpinner />
      ) : orders.length === 0 ? (
        <p className="text-muted">You haven't placed any orders yet.</p>
      ) : (
        <div className="orders-table-wrap">
          <table className="orders-table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Date</th>
                <th>Items</th>
                <th>Total</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(order => (
                <tr key={order.id}>
                  <td className="order-id">#{order.id.slice(0, 8).toUpperCase()}</td>
                  <td>{new Date(order.created_at).toLocaleDateString()}</td>
                  <td>{order.items.reduce((s, i) => s + i.quantity, 0)} card(s)</td>
                  <td>${order.total.toFixed(2)}</td>
                  <td><span className="badge badge--success">Completed</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

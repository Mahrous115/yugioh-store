import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'

import Home                 from './pages/Home'
import Catalog              from './pages/Catalog'
import CardDetail           from './pages/CardDetail'
import Cart                 from './pages/Cart'
import CheckoutConfirmation from './pages/CheckoutConfirmation'
import Wishlist             from './pages/Wishlist'
import Profile              from './pages/Profile'
import Admin                from './pages/Admin'
import Login                from './pages/Login'
import Register             from './pages/Register'

export default function App() {
  return (
    <>
      <Navbar />

      <main className="main-content">
        <Routes>
          <Route path="/"            element={<Home />} />
          <Route path="/catalog"     element={<Catalog />} />
          <Route path="/cards/:id"   element={<CardDetail />} />
          <Route path="/cart"        element={<Cart />} />
          <Route path="/login"       element={<Login />} />
          <Route path="/register"    element={<Register />} />

          <Route path="/checkout/confirmation" element={
            <ProtectedRoute><CheckoutConfirmation /></ProtectedRoute>
          } />
          <Route path="/wishlist" element={
            <ProtectedRoute><Wishlist /></ProtectedRoute>
          } />
          <Route path="/profile" element={
            <ProtectedRoute><Profile /></ProtectedRoute>
          } />
          <Route path="/admin" element={
            <AdminRoute><Admin /></AdminRoute>
          } />

          {/* 404 fallback */}
          <Route path="*" element={
            <div className="page">
              <div className="empty-state">
                <span className="empty-state__icon">🃏</span>
                <h2>Page not found</h2>
              </div>
            </div>
          } />
        </Routes>
      </main>

      <footer className="footer">
        <p>© {new Date().getFullYear()} Duel Market — Demo project. Card data by <a href="https://ygoprodeck.com" target="_blank" rel="noreferrer">YGOPRODeck</a>.</p>
      </footer>
    </>
  )
}

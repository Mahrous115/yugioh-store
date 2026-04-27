import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useCart } from '../context/CartContext'

export default function Navbar() {
  const { user, profile, isAdmin, signOut } = useAuth()
  const { itemCount } = useCart()
  const navigate      = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  async function handleSignOut() {
    await signOut()
    navigate('/')
    setMenuOpen(false)
  }

  const close = () => setMenuOpen(false)

  return (
    <nav className="navbar">
      <Link to="/" className="navbar__logo" onClick={close}>
        <span className="navbar__logo-star">★</span> Duel Market
      </Link>

      {/* Hamburger (mobile) */}
      <button
        className={`navbar__burger ${menuOpen ? 'navbar__burger--open' : ''}`}
        onClick={() => setMenuOpen(o => !o)}
        aria-label="Toggle menu"
      >
        <span /><span /><span />
      </button>

      <div className={`navbar__links ${menuOpen ? 'navbar__links--open' : ''}`}>
        <NavLink to="/catalog" className="navbar__link" onClick={close}>Catalog</NavLink>

        <NavLink to="/cart" className="navbar__link navbar__cart" onClick={close}>
          Cart
          {itemCount > 0 && <span className="navbar__badge">{itemCount}</span>}
        </NavLink>

        {user ? (
          <>
            <NavLink to="/wishlist" className="navbar__link" onClick={close}>Wishlist</NavLink>
            <NavLink to="/profile"  className="navbar__link" onClick={close}>
              {profile?.username?.split('@')[0] ?? 'Profile'}
            </NavLink>
            {isAdmin && (
              <NavLink to="/admin" className="navbar__link navbar__link--admin" onClick={close}>
                Admin
              </NavLink>
            )}
            <button className="btn btn--ghost btn--sm" onClick={handleSignOut}>Log out</button>
          </>
        ) : (
          <>
            <NavLink to="/login"    className="navbar__link" onClick={close}>Log in</NavLink>
            <NavLink to="/register" className="btn btn--gold btn--sm" onClick={close}>Sign up</NavLink>
          </>
        )}
      </div>
    </nav>
  )
}

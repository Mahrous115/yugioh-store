import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider }     from './context/AuthContext'
import { CartProvider }     from './context/CartContext'
import { WishlistProvider } from './context/WishlistContext'
import { ListingsProvider } from './context/ListingsContext'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      {/* Auth must wrap Wishlist because WishlistProvider reads the current user */}
      <AuthProvider>
        {/* Listings wraps Cart so checkout can refresh stock after an order */}
        <ListingsProvider>
          <CartProvider>
            <WishlistProvider>
              <App />
            </WishlistProvider>
          </CartProvider>
        </ListingsProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)

// Re-exports WishlistContext as a hook so call-sites stay unchanged.
// The actual state lives in WishlistContext (loaded once, shared everywhere).
export { useWishlistContext as useWishlist } from '../context/WishlistContext'

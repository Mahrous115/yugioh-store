import { useEffect, useState } from 'react'
import { getListings, createListing, updateListing, deleteListing } from '../services/api'
import { searchCards } from '../services/ygoprodeck'
import LoadingSpinner from '../components/LoadingSpinner'

export default function Admin() {
  const [listings,    setListings]    = useState([])
  const [loadingList, setLoadingList] = useState(true)
  const [editingId,   setEditingId]   = useState(null)
  const [editForm,    setEditForm]    = useState({ price: '', stock: '' })
  const [error,       setError]       = useState('')
  const [success,     setSuccess]     = useState('')

  // ── Card search state for "Add Listing" form ──────────────
  const [query,        setQuery]        = useState('')
  const [searchRes,    setSearchRes]    = useState([])
  const [searching,    setSearching]    = useState(false)
  const [selectedCard, setSelectedCard] = useState(null)
  const [newPrice,     setNewPrice]     = useState('')
  const [newStock,     setNewStock]     = useState('')
  const [adding,       setAdding]       = useState(false)

  useEffect(() => { loadListings() }, [])

  async function loadListings() {
    setLoadingList(true)
    try { setListings(await getListings()) }
    finally { setLoadingList(false) }
  }

  // Debounced card search
  useEffect(() => {
    if (!query.trim()) { setSearchRes([]); return }
    const id = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await searchCards({ fname: query, num: 10 })
        setSearchRes(res.data)
      } finally { setSearching(false) }
    }, 400)
    return () => clearTimeout(id)
  }, [query])

  function selectCard(card) {
    setSelectedCard(card)
    setSearchRes([])
    setQuery(card.name)
  }

  async function handleAdd(e) {
    e.preventDefault()
    if (!selectedCard) { setError('Select a card first'); return }
    setAdding(true); setError(''); setSuccess('')
    try {
      await createListing({
        card_id:    selectedCard.id,
        card_name:  selectedCard.name,
        card_image: selectedCard.card_images[0].image_url,
        price:      parseFloat(newPrice),
        stock:      parseInt(newStock, 10),
      })
      setSuccess(`Listing for "${selectedCard.name}" created.`)
      setSelectedCard(null); setQuery(''); setNewPrice(''); setNewStock('')
      loadListings()
    } catch (e) { setError(e.message) }
    finally { setAdding(false) }
  }

  async function handleSaveEdit(id) {
    try {
      await updateListing(id, {
        price: parseFloat(editForm.price),
        stock: parseInt(editForm.stock, 10),
      })
      setEditingId(null)
      loadListings()
    } catch (e) { setError(e.message) }
  }

  async function handleDelete(id, name) {
    if (!window.confirm(`Delete listing for "${name}"?`)) return
    try {
      await deleteListing(id)
      loadListings()
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="page">
      <h1 className="page__title">Admin Dashboard</h1>

      {error   && <div className="alert alert--error">{error}</div>}
      {success && <div className="alert alert--success">{success}</div>}

      {/* ── Add new listing ─────────────────────────────────── */}
      <section className="admin-section">
        <h2 className="admin-section__title">Add New Listing</h2>
        <form className="admin-form" onSubmit={handleAdd}>
          <div className="admin-form__search-wrap">
            <input
              className="form-input"
              placeholder="Search card by name…"
              value={query}
              onChange={e => { setQuery(e.target.value); setSelectedCard(null) }}
            />
            {searching && <p className="admin-form__hint">Searching…</p>}
            {searchRes.length > 0 && (
              <ul className="card-search-results">
                {searchRes.map(c => (
                  <li key={c.id} className="card-search-results__item" onClick={() => selectCard(c)}>
                    <img src={c.card_images[0].image_url_small} alt={c.name} />
                    <span>{c.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {selectedCard && (
            <div className="admin-form__selected">
              <img src={selectedCard.card_images[0].image_url_small} alt={selectedCard.name} />
              <span>{selectedCard.name} (ID: {selectedCard.id})</span>
            </div>
          )}

          <div className="admin-form__row">
            <label className="form-label">
              Price ($)
              <input
                className="form-input"
                type="number"
                min="0.01"
                step="0.01"
                value={newPrice}
                onChange={e => setNewPrice(e.target.value)}
                required
              />
            </label>
            <label className="form-label">
              Stock
              <input
                className="form-input"
                type="number"
                min="0"
                value={newStock}
                onChange={e => setNewStock(e.target.value)}
                required
              />
            </label>
          </div>

          <button className="btn btn--gold" type="submit" disabled={adding}>
            {adding ? 'Adding…' : 'Add Listing'}
          </button>
        </form>
      </section>

      {/* ── Manage existing listings ─────────────────────────── */}
      <section className="admin-section">
        <h2 className="admin-section__title">Manage Listings ({listings.length})</h2>

        {loadingList ? <LoadingSpinner /> : (
          listings.length === 0 ? (
            <p className="text-muted">No listings yet. Add one above.</p>
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Card</th>
                    <th>Price</th>
                    <th>Stock</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {listings.map(l => (
                    <tr key={l.id}>
                      <td className="admin-table__card">
                        <img src={l.card_image} alt={l.card_name} />
                        <span>{l.card_name}</span>
                      </td>

                      {editingId === l.id ? (
                        <>
                          <td>
                            <input
                              className="form-input form-input--sm"
                              type="number"
                              min="0.01"
                              step="0.01"
                              value={editForm.price}
                              onChange={e => setEditForm(f => ({ ...f, price: e.target.value }))}
                            />
                          </td>
                          <td>
                            <input
                              className="form-input form-input--sm"
                              type="number"
                              min="0"
                              value={editForm.stock}
                              onChange={e => setEditForm(f => ({ ...f, stock: e.target.value }))}
                            />
                          </td>
                          <td className="admin-table__actions">
                            <button className="btn btn--gold btn--sm" onClick={() => handleSaveEdit(l.id)}>Save</button>
                            <button className="btn btn--ghost btn--sm" onClick={() => setEditingId(null)}>Cancel</button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td>${l.price.toFixed(2)}</td>
                          <td>{l.stock}</td>
                          <td className="admin-table__actions">
                            <button
                              className="btn btn--ghost btn--sm"
                              onClick={() => { setEditingId(l.id); setEditForm({ price: l.price, stock: l.stock }) }}
                            >Edit</button>
                            <button
                              className="btn btn--danger btn--sm"
                              onClick={() => handleDelete(l.id, l.card_name)}
                            >Delete</button>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </section>
    </div>
  )
}

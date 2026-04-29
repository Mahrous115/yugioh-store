import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { getListings, createListing, updateListing, deleteListing } from '../services/api'
import { searchCards } from '../services/ygoprodeck'
import { supabase } from '../services/supabase'
import LoadingSpinner from '../components/LoadingSpinner'

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-3)',
      border: '1px solid var(--border-gold)',
      borderRadius: 'var(--radius-sm)',
      padding: '0.5rem 0.75rem',
    }}>
      <p style={{ color: 'var(--text-2)', margin: '0 0 0.25rem', fontSize: '0.8rem' }}>{label}</p>
      <p style={{ color: 'var(--gold)', margin: 0, fontWeight: 600 }}>${payload[0].value.toFixed(2)}</p>
    </div>
  )
}

export default function Admin() {
  // ── Analytics state ───────────────────────────────────────
  const [analytics,        setAnalytics]        = useState(null)
  const [loadingAnalytics, setLoadingAnalytics] = useState(true)

  // ── Listings state ────────────────────────────────────────
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

  useEffect(() => { loadListings() },  [])
  useEffect(() => { loadAnalytics() }, [])

  async function loadAnalytics() {
    try {
      const { data: orders } = await supabase
        .from('orders')
        .select('total, items, created_at')
        .order('created_at', { ascending: true })

      const rows = orders ?? []

      const totalOrders  = rows.length
      const totalRevenue = rows.reduce((sum, o) => sum + parseFloat(o.total), 0)

      // Aggregate quantity sold per card across all orders
      const productMap = {}
      for (const order of rows) {
        const items = Array.isArray(order.items) ? order.items : []
        for (const item of items) {
          const name = item.card_name
          productMap[name] = (productMap[name] || 0) + (item.quantity || 1)
        }
      }
      const topProducts = Object.entries(productMap)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
        .map(([name, qty]) => ({ name, qty }))

      // Daily revenue for the chart
      const revenueByDate = {}
      for (const order of rows) {
        const date = order.created_at.slice(0, 10)
        revenueByDate[date] = (revenueByDate[date] || 0) + parseFloat(order.total)
      }
      const revenueChart = Object.entries(revenueByDate)
        .map(([date, revenue]) => ({ date, revenue: +revenue.toFixed(2) }))

      setAnalytics({ totalOrders, totalRevenue, topProducts, revenueChart })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoadingAnalytics(false)
    }
  }

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

      {/* ── Analytics ─────────────────────────────────────────── */}
      <section className="admin-section">
        <h2 className="admin-section__title">Analytics</h2>

        {loadingAnalytics ? <LoadingSpinner /> : analytics && (
          <>
            {/* Stat cards */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '1rem',
              marginBottom: '2rem',
            }}>
              {[
                { label: 'Total Orders',  value: analytics.totalOrders },
                { label: 'Total Revenue', value: `$${analytics.totalRevenue.toFixed(2)}` },
              ].map(({ label, value }) => (
                <div key={label} style={{
                  background: 'var(--bg-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                  padding: '1.25rem 1.5rem',
                }}>
                  <p style={{ color: 'var(--text-2)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.08em', margin: '0 0 0.4rem' }}>
                    {label}
                  </p>
                  <p style={{ color: 'var(--gold)', fontSize: '1.9rem', fontWeight: 700, margin: 0 }}>
                    {value}
                  </p>
                </div>
              ))}
            </div>

            {/* Top 5 products */}
            <h3 style={{ color: 'var(--text-1)', fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Top 5 Products
            </h3>
            {analytics.topProducts.length === 0 ? (
              <p className="text-muted" style={{ marginBottom: '2rem' }}>No order data yet.</p>
            ) : (
              <div className="admin-table-wrap" style={{ marginBottom: '2rem' }}>
                <table className="admin-table">
                  <thead>
                    <tr><th>#</th><th>Card</th><th>Qty Sold</th></tr>
                  </thead>
                  <tbody>
                    {analytics.topProducts.map(({ name, qty }, i) => (
                      <tr key={name}>
                        <td style={{ color: 'var(--text-3)', width: '2.5rem' }}>{i + 1}</td>
                        <td>{name}</td>
                        <td style={{ color: 'var(--gold)', fontWeight: 600 }}>{qty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Revenue over time */}
            <h3 style={{ color: 'var(--text-1)', fontSize: '0.95rem', fontWeight: 600, margin: '0 0 0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Revenue Over Time
            </h3>
            {analytics.revenueChart.length === 0 ? (
              <p className="text-muted">No order data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={analytics.revenueChart} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                  <XAxis
                    dataKey="date"
                    tick={{ fill: 'var(--text-2)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: 'var(--text-2)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={v => `$${v}`}
                    width={54}
                  />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(201,162,39,0.08)' }} />
                  <Bar dataKey="revenue" fill="var(--gold)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </>
        )}
      </section>

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

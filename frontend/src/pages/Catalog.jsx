import { useEffect, useState, useCallback } from 'react'
import { searchCards, loadDefaultCatalog } from '../services/ygoprodeck'
import { getListings } from '../services/api'
import FilterBar from '../components/FilterBar'
import CardGrid from '../components/CardGrid'

const PAGE_SIZE = 20

export default function Catalog() {
  const [cards,      setCards]      = useState([])
  const [listingMap, setListingMap] = useState(new Map())
  const [loading,    setLoading]    = useState(true)
  const [total,      setTotal]      = useState(0)
  const [offset,     setOffset]     = useState(0)
  const [filters,    setFilters]    = useState({ fname: '', type: '', attribute: '', race: '' })

  // Load custom listings once (they don't change during a session)
  useEffect(() => {
    getListings().then(list => setListingMap(new Map(list.map(l => [l.card_id, l]))))
  }, [])

  const fetchCards = useCallback(async (currentFilters, currentOffset) => {
    setLoading(true)
    try {
      const hasFilter = Object.values(currentFilters).some(Boolean)
      const res = hasFilter
        ? await searchCards({ ...currentFilters, num: PAGE_SIZE, offset: currentOffset })
        : await loadDefaultCatalog(PAGE_SIZE, currentOffset)

      setCards(res.data)
      setTotal(res.meta?.total_rows ?? res.data.length)
    } catch (e) {
      console.error(e)
      setCards([])
    } finally {
      setLoading(false)
    }
  }, [])

  // Re-fetch whenever filters or offset change
  useEffect(() => { fetchCards(filters, offset) }, [filters, offset, fetchCards])

  function handleFilter(newFilters) {
    setFilters(newFilters)
    setOffset(0) // Reset to first page on new search
  }

  const totalPages  = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Card Catalog</h1>
        {!loading && <p className="page__count">{total.toLocaleString()} cards found</p>}
      </div>

      <FilterBar onFilter={handleFilter} />

      <CardGrid cards={cards} listingMap={listingMap} loading={loading} />

      {!loading && totalPages > 1 && (
        <div className="pagination">
          <button
            className="btn btn--ghost btn--sm"
            disabled={offset === 0}
            onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))}
          >
            ← Prev
          </button>
          <span className="pagination__info">Page {currentPage} / {totalPages}</span>
          <button
            className="btn btn--ghost btn--sm"
            disabled={offset + PAGE_SIZE >= total || cards.length < PAGE_SIZE}
            onClick={() => setOffset(o => o + PAGE_SIZE)}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}

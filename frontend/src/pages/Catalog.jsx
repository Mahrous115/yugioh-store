import { useEffect, useState, useCallback } from 'react'
import { searchCards, loadDefaultCatalog } from '../services/ygoprodeck'
import { useListings } from '../context/ListingsContext'
import FilterBar from '../components/FilterBar'
import CardGrid from '../components/CardGrid'

const PAGE_SIZE = 20

export default function Catalog() {
  const [cards,      setCards]      = useState([])
  const [loading,    setLoading]    = useState(true)
  const [total,      setTotal]      = useState(0)
  const [offset,     setOffset]     = useState(0)
  const [filters,    setFilters]    = useState({ fname: '', type: '', attribute: '', race: '' })

  // Listings come from the shared store rather than a local fetch. They used to be
  // loaded once here, on the assumption that they never change during a session --
  // no longer true now that a purchase decrements stock.
  const { byCardId: listingMap } = useListings()

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

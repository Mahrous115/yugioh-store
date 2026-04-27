// Thin wrapper around the public YGOPRODeck REST API
// Docs: https://ygoprodeck.com/api-guide/
const BASE = 'https://db.ygoprodeck.com/api/v7/cardinfo.php'

/**
 * Search / filter cards with optional pagination.
 * Returns { data: Card[], meta: { total_rows, rows_returned } }
 * Returns { data: [], meta: { total_rows: 0 } } when no cards match.
 */
export async function searchCards({
  fname = '',
  type = '',
  attribute = '',
  race = '',
  num = 20,
  offset = 0,
} = {}) {
  const params = new URLSearchParams()
  if (fname)     params.set('fname', fname)
  if (type)      params.set('type', type)
  if (attribute) params.set('attribute', attribute)
  if (race)      params.set('race', race)
  params.set('num', String(num))
  params.set('offset', String(offset))

  const res = await fetch(`${BASE}?${params}`)

  // 400 = "No card matching your query was found."
  if (res.status === 400) return { data: [], meta: { total_rows: 0, rows_returned: 0 } }
  if (!res.ok) throw new Error(`YGOPRODeck API error: ${res.status}`)
  return res.json()
}

/**
 * Fetch a single card by its numeric YGOPRODeck ID.
 * Throws if not found.
 */
export async function getCardById(id) {
  const res = await fetch(`${BASE}?id=${id}`)
  if (!res.ok) throw new Error('Card not found')
  const json = await res.json()
  return json.data[0]
}

/**
 * Convenience: load the default catalog page (offset 0, no filters).
 * Used for initial render of the catalog before the user types.
 */
export const loadDefaultCatalog = (num = 20, offset = 0) =>
  searchCards({ num, offset })

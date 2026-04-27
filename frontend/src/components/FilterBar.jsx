import { useState, useEffect } from 'react'

const CARD_TYPES = [
  '', 'Effect Monster', 'Normal Monster', 'Ritual Monster',
  'Fusion Monster', 'Synchro Monster', 'Xyz Monster', 'Link Monster',
  'Spell Card', 'Trap Card',
]

const ATTRIBUTES = ['', 'DARK', 'LIGHT', 'EARTH', 'WATER', 'FIRE', 'WIND', 'DIVINE']

const RACES = [
  '', 'Dragon', 'Spellcaster', 'Warrior', 'Fiend', 'Fairy',
  'Beast', 'Machine', 'Aqua', 'Zombie', 'Thunder', 'Pyro',
  'Rock', 'Plant', 'Insect', 'Dinosaur', 'Beast-Warrior', 'Cyberse',
]

/**
 * Search input (debounced 400 ms) + type / attribute / race dropdowns.
 * Calls onFilter({ fname, type, attribute, race }) whenever any value changes.
 */
export default function FilterBar({ onFilter }) {
  const [fname,     setFname]     = useState('')
  const [type,      setType]      = useState('')
  const [attribute, setAttribute] = useState('')
  const [race,      setRace]      = useState('')

  // Debounce the text input so we don't fire a request on every keystroke
  useEffect(() => {
    const id = setTimeout(() => onFilter({ fname, type, attribute, race }), 400)
    return () => clearTimeout(id)
  }, [fname, type, attribute, race]) // eslint-disable-line react-hooks/exhaustive-deps

  function reset() {
    setFname(''); setType(''); setAttribute(''); setRace('')
  }

  const isDirty = fname || type || attribute || race

  return (
    <div className="filter-bar">
      <input
        className="filter-bar__search"
        type="text"
        placeholder="Search cards by name…"
        value={fname}
        onChange={e => setFname(e.target.value)}
      />

      <select className="filter-bar__select" value={type}      onChange={e => setType(e.target.value)}>
        <option value="">All Types</option>
        {CARD_TYPES.slice(1).map(t => <option key={t} value={t}>{t}</option>)}
      </select>

      <select className="filter-bar__select" value={attribute} onChange={e => setAttribute(e.target.value)}>
        <option value="">All Attributes</option>
        {ATTRIBUTES.slice(1).map(a => <option key={a} value={a}>{a}</option>)}
      </select>

      <select className="filter-bar__select" value={race}      onChange={e => setRace(e.target.value)}>
        <option value="">All Races</option>
        {RACES.slice(1).map(r => <option key={r} value={r}>{r}</option>)}
      </select>

      {isDirty && (
        <button className="btn btn--ghost btn--sm" onClick={reset}>Clear</button>
      )}
    </div>
  )
}

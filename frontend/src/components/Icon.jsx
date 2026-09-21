/**
 * Inline SVG icon set.
 *
 * Replaces the emoji and typographic glyphs this UI used to draw icons with:
 * playing-card, shopping-cart and envelope emoji, plus star, heart, tick, cross,
 * minus and arrow characters. Those rendered at the mercy of whichever font the
 * OS picked — full-colour emoji on one machine, a monochrome glyph or a tofu
 * box on another — sat on their own baseline, and could not be recoloured.
 *
 * Every icon here is a 24×24 path drawn in `currentColor`, so it inherits the
 * colour of whatever it sits in and scales with `size` instead of `font-size`.
 */

// `solid: true` means the shape is filled rather than stroked.
const ICONS = {
  star: {
    solid: true,
    paths: ['M12 2.4l2.94 5.96 6.58.96-4.76 4.64 1.12 6.55L12 17.42l-5.88 3.09 1.12-6.55L2.48 9.32l6.58-.96L12 2.4z'],
  },
  heart: {
    paths: ['M12 20.35l-1.45-1.32C5.4 14.36 2 11.28 2 7.5 2 4.88 4.09 2.8 6.7 2.8c1.48 0 2.9.69 3.82 1.78L12 6.1l1.48-1.52c.92-1.09 2.34-1.78 3.82-1.78C19.91 2.8 22 4.88 22 7.5c0 3.78-3.4 6.86-8.55 11.54L12 20.35z'],
  },
  cart: {
    paths: [
      'M2.5 3.5h2.4l2.5 11.3a1.7 1.7 0 0 0 1.66 1.33h8.2a1.7 1.7 0 0 0 1.65-1.28L20.7 8H6',
      'M9.6 20.3a1.35 1.35 0 1 0 0-2.7 1.35 1.35 0 0 0 0 2.7z',
      'M17.6 20.3a1.35 1.35 0 1 0 0-2.7 1.35 1.35 0 0 0 0 2.7z',
    ],
  },
  cards: {
    paths: [
      'M10 2.9h8.1a2 2 0 0 1 2 2v10.4a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V4.9a2 2 0 0 1 2-2z',
      'M4.6 6.6v11.5a3 3 0 0 0 3 3h9',
    ],
  },
  mail: {
    paths: [
      'M4 4.9h16a2 2 0 0 1 2 2v10.2a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6.9a2 2 0 0 1 2-2z',
      'M2.4 6.4l9.6 6.3 9.6-6.3',
    ],
  },
  check:      { paths: ['M20 6.5L9.2 17.3 4 12.1'] },
  x:          { paths: ['M17.8 6.2L6.2 17.8', 'M6.2 6.2l11.6 11.6'] },
  minus:      { paths: ['M5 12h14'] },
  plus:       { paths: ['M12 5v14', 'M5 12h14'] },
  arrowLeft:  { paths: ['M19 12H5', 'M11.6 18.4L5.2 12l6.4-6.4'] },
  arrowRight: { paths: ['M5 12h14', 'M12.4 5.6L18.8 12l-6.4 6.4'] },
}

/**
 * @param name    key into ICONS
 * @param size    rendered px, both dimensions
 * @param filled  draw an outline icon solid — used for the wishlist heart,
 *                where filled/hollow is what tells you the current state
 * @param title   accessible name. Omit when neighbouring text or an aria-label
 *                on the parent button already names the control; the icon is
 *                then hidden from assistive tech rather than read twice.
 */
export default function Icon({ name, size = 20, filled = false, className = '', title, ...rest }) {
  const icon = ICONS[name]
  if (!icon) return null

  const solid = icon.solid || filled

  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={solid ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={solid ? 0 : 1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
      {...rest}
    >
      {title && <title>{title}</title>}
      {icon.paths.map(d => <path key={d} d={d} />)}
    </svg>
  )
}

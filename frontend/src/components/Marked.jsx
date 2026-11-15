/** Renders ``[{text, match}]`` segments. Text is never interpreted as HTML. */
export function Marked({ segments }) {
  return segments.map((seg, i) => (seg.match ? <mark key={i}>{seg.text}</mark> : <span key={i}>{seg.text}</span>));
}

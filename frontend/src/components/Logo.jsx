export function Logo({ size = "small", onClick }) {
  return (
    <button type="button" className={`logo logo-${size}`} onClick={onClick} aria-label="Clea home">
      Clea
    </button>
  );
}

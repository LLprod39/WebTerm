/**
 * Decorative atmosphere for the ASHITA skin only.
 * Presentational: no state, no business logic, pointer-events none.
 */
export function AshitaAtmosphere() {
  return (
    <div className="ashita-atmosphere" aria-hidden="true">
      <div className="ashita-atmosphere__grain" />
      <div className="ashita-atmosphere__scanlines" />
      <div className="ashita-atmosphere__roof" />
      <div className="ashita-atmosphere__petals">
        <span className="ashita-petal ashita-petal--1" />
        <span className="ashita-petal ashita-petal--2" />
        <span className="ashita-petal ashita-petal--3" />
        <span className="ashita-petal ashita-petal--4" />
        <span className="ashita-petal ashita-petal--5" />
      </div>
    </div>
  );
}

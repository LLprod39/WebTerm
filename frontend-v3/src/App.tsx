export default function App() {
  return (
    <div className="app-shell" data-theme="dark">
      <aside className="sidebar">
        <h1>WebTerm</h1>
        <nav aria-label="Primary">
          <a href="/dashboard" aria-current="page">
            Dashboard
          </a>
          <a href="/servers">Servers</a>
          <a href="/login">Login</a>
        </nav>
      </aside>
      <main className="main">
        <div className="topbar">
          <button type="button" aria-label="Toggle theme" disabled>
            Theme
          </button>
        </div>
        <h2>frontend-v3 skeleton</h2>
        <p>
          Dark monochrome shell on :8081. Proxy targets backend :9000. UI work
          continues from here — no decorative metrics.
        </p>
      </main>
    </div>
  );
}
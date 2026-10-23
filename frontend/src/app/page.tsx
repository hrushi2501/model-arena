export default function HomePage() {
  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Model Arena home">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>Model Arena</span>
        </a>
        <span className="environment-badge">LOCAL DEVELOPMENT</span>
      </header>

      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">SAFE MODEL RELEASE CONTROL PLANE</p>
        <h1 id="page-title">Every model earns its traffic.</h1>
        <p className="hero-copy">
          Compare a candidate in shadow mode, send it a measured share of traffic, and promote or
          roll back with evidence.
        </p>

        <div className="connection-card" role="status">
          <span className="status-dot" aria-hidden="true" />
          <div>
            <strong>Control API not connected</strong>
            <p>This starter screen has no live model or rollout data yet.</p>
          </div>
        </div>
      </section>

      <section className="starter-grid" aria-label="Model Arena areas">
        <article className="starter-card">
          <span className="card-index">01</span>
          <h2>Model registry</h2>
          <p>Registered versions, evaluation results, and champion or candidate roles.</p>
        </article>
        <article className="starter-card">
          <span className="card-index">02</span>
          <h2>Rollout control</h2>
          <p>Shadow, canary traffic, hold, promotion, and rollback controls.</p>
        </article>
        <article className="starter-card">
          <span className="card-index">03</span>
          <h2>Decision history</h2>
          <p>Evidence and reasons behind each automatic or manual release decision.</p>
        </article>
      </section>

      <footer className="page-footer">
        <span>Model Arena</span>
        <span>Training pipeline and serving controls are scaffolded separately.</span>
      </footer>
    </main>
  );
}

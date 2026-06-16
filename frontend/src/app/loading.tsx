export default function Loading() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", width: "100%" }}>
      {/* Skeleton Top Bar */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap", opacity: 0.5 }}>
        <div style={{ width: "60px", height: "24px", background: "var(--bg-elevated)", borderRadius: "4px" }} className="animate-pulse" />
        <div style={{ width: "1px", height: "20px", background: "var(--border-bright)", flexShrink: 0 }} />
        <div style={{ width: "150px", height: "20px", background: "var(--bg-elevated)", borderRadius: "4px" }} className="animate-pulse" />
      </div>

      <div className="dashboard-grid">
        {/* LEVÝ SLOUPEC: Score Overview + Týdenní výhled */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="card animate-pulse" style={{ height: "300px", background: "var(--bg-card)" }} />
          <div className="card animate-pulse" style={{ height: "250px", background: "var(--bg-card)" }} />
        </div>

        {/* PRAVÝ SLOUPEC: Graf + Sentiment gauges + Events */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px", minWidth: 0 }}>
          <div className="card animate-pulse" style={{ height: "320px", background: "var(--bg-card)" }} />

          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", width: "100%" }}>
            <div className="card animate-pulse" style={{ height: "200px", flex: 1, minWidth: "220px", background: "var(--bg-card)" }} />
            <div className="card animate-pulse" style={{ height: "200px", flex: 1, minWidth: "220px", background: "var(--bg-card)" }} />
            <div className="card animate-pulse" style={{ height: "200px", flex: 1, minWidth: "280px", background: "var(--bg-card)" }} />
          </div>

          <div className="card animate-pulse" style={{ height: "400px", background: "var(--bg-card)" }} />
        </div>
      </div>
    </div>
  );
}

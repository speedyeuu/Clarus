import ScoreOverview from "@/components/ScoreOverview";
import ScoreChart from "@/components/ScoreChart";
import EventsPanel from "@/components/EventsPanel";
import { fetchLatestScore, fetchScoreHistory, fetchPredictions, fetchUpcomingEvents } from "@/lib/api";

// Next.js serverový komponent
export default async function DashboardPage() {
  
  // Tím že to běží na serveru zavoláme náš FastAPI backend paralelně 
  // a teprve s výsledkem vykreslíme stránku bez blikání = super rychlé.
  let today_score = null;
  let history = [];
  let predictions = [];
  let events = [];
  
  let error_msg = null;

  try {
    const [latestRes, historyRes, predRes, eventsRes] = await Promise.all([
      fetchLatestScore(),
      fetchScoreHistory(30),
      fetchPredictions(),
      fetchUpcomingEvents(7)
    ]);
    
    today_score = latestRes;
    history = historyRes;
    predictions = predRes;
    events = eventsRes;
    
  } catch (err: any) {
    console.error("Failed to fetch from backend API:", err);
    error_msg = "Máme potíže s připojením k našemu Python serveru. Běží na backendu `uvicorn main:app`?";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Top status bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px",
        background: "var(--bg-card)",
        borderRadius: "8px",
        border: "1px solid var(--border)",
        fontSize: "12px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div className={`live-dot ${error_msg ? "error_red" : ""}`} />
            <span style={{ color: "var(--text-secondary)" }}>
              Data načtena naživo ze severu
            </span>
          </div>
          <span style={{ color: "var(--border-bright)" }}>|</span>
          <span style={{ color: "var(--text-muted)" }}>
             {today_score?.date ? `Aktualizováno k ${new Date(today_score.date).toLocaleDateString("cs-CZ")}` : "Žádná data z dneška"}
          </span>
        </div>
        
        {error_msg ? (
           <div style={{
            fontSize: "11px", color: "var(--bearish)", fontWeight: 600,
            background: "var(--bearish-dim)", padding: "2px 8px", borderRadius: "4px",
          }}>
            🔌 Chybí spojení
          </div>
        ) : (
          <div style={{
            fontSize: "11px", color: "var(--bullish)", fontWeight: 600,
            background: "var(--bullish-dim)", padding: "2px 8px", borderRadius: "4px",
          }}>
            ✔️ Live API (Supabase)
          </div>
        )}
      </div>

      {/* Chyba při pádu, abychom viděli proč to prázdní */}
      {error_msg && (
        <div style={{ padding: "20px", background: "var(--bearish-dim)", color: "var(--bearish)", border: "1px solid var(--border)", borderRadius: "8px" }}>
          <strong>Chyba:</strong> {error_msg}
        </div>
      )}

      {/* Main grid */}
      {!error_msg && today_score && (
        <div className="dashboard-grid">
          {/* Left: Score Overview */}
          <ScoreOverview score={today_score} />

          {/* Right: Chart + Events */}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <ScoreChart history={history} predictions={predictions} />
            <EventsPanel events={events} />
          </div>
        </div>
      )}
    </div>
  );
}

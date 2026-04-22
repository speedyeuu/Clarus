import ScoreOverview from "@/components/ScoreOverview";
import ScoreChart from "@/components/ScoreChart";
import EventsPanel from "@/components/EventsPanel";
import IndicatorHistoryChart from "@/components/IndicatorHistoryChart";
import { fetchLatestScore, fetchScoreHistory, fetchPredictions, fetchUpcomingEvents } from "@/lib/api";
import type { DailyScore, Prediction, UpcomingEvent } from "@/lib/types";

// Next.js serverový komponent
export default async function DashboardPage() {
  
  // Tím že to běží na serveru zavoláme náš FastAPI backend paralelně 
  // a teprve s výsledkem vykreslíme stránku bez blikání = super rychlé.
  let today_score: DailyScore | null = null;
  let history: DailyScore[] = [];
  let predictions: Prediction[] = [];
  let events: UpcomingEvent[] = [];
  
  let error_msg: string | null = null;

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
      {/* Chyba při pádu backendu */}
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
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", minWidth: 0 }}>
            <ScoreChart history={history} predictions={predictions} />
            
            {/* Vložené sekundární grafy pro Retail a COT */}
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", width: "100%" }}>
              <IndicatorHistoryChart 
                title="Retail Sentiment" 
                dataKey="score_retail_sentiment"
                history={history} 
                tooltip="Kontraindikátor! Ukazuje pozice malých retailových obchodníků. Pokud 80 % retailu shortuje EUR/USD, velcí hráči jsou pravděpodobně na opačné straně → bullish signál. Dav se mýlí — sledujeme ho obráceně."
              />
              <IndicatorHistoryChart 
                title="COT Bias" 
                dataKey="score_cot"
                history={history} 
                tooltip="Ukazuje, jak velcí institucionální hráči drží pozice na EUR a americkém dolaru. Silná net-long pozice na EUR = smart money čeká posílení EUR — jde o spolehlivý dlouhodobý sentiment indikátor."
              />
            </div>

            <EventsPanel events={events} />
          </div>
        </div>
      )}
    </div>
  );
}

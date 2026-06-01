import ScoreOverview from "@/components/ScoreOverview";
import ScoreChart from "@/components/ScoreChart";
import EventsPanel from "@/components/EventsPanel";
import SentimentGaugeChart from "@/components/SentimentGaugeChart";
import TechnicalPanel from "@/components/TechnicalPanel";
import WeekSummaryPanel from "@/components/WeekSummaryPanel";
import {
  fetchLatestScore,
  fetchScoreHistory,
  fetchPredictions,
  fetchUpcomingEvents,
  fetchAccuracySummary,
  fetchTechnicalAnalysis,
  fetchWeekSummary,
} from "@/lib/api";
import type { DailyScore, Prediction, UpcomingEvent, AccuracySummary } from "@/lib/types";

export default async function DashboardPage() {
  let today_score: DailyScore | null = null;
  let history: DailyScore[] = [];
  let predictions: Prediction[] = [];
  let events: UpcomingEvent[] = [];
  let accuracy: AccuracySummary = { week_avg: null, month_avg: null, week_count: 0, month_count: 0 };
  let technical = null;
  let weekSummary = null;
  let error_msg: string | null = null;

  try {
    const [latestRes, historyRes, predRes, eventsRes, accuracyRes, techRes, weekRes] = await Promise.all([
      fetchLatestScore(),
      fetchScoreHistory(30),
      fetchPredictions(),
      fetchUpcomingEvents(7),
      fetchAccuracySummary(),
      fetchTechnicalAnalysis(),
      fetchWeekSummary(),
    ]);
    today_score = latestRes;
    history = historyRes;
    predictions = predRes;
    events = eventsRes;
    accuracy = accuracyRes;
    technical = techRes;
    weekSummary = weekRes;
  } catch (err: any) {
    console.error("Failed to fetch from backend API:", err);
    error_msg = "Máme potíže s připojením k našemu Python serveru. Běží na backendu `uvicorn main:app`?";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {error_msg && (
        <div style={{ padding: "20px", background: "var(--bearish-dim)", color: "var(--bearish)", border: "1px solid var(--border)", borderRadius: "8px" }}>
          <strong>Chyba:</strong> {error_msg}
        </div>
      )}

      {!error_msg && today_score && (
        <div className="dashboard-grid">
          <ScoreOverview score={today_score} />

          <div style={{ display: "flex", flexDirection: "column", gap: "16px", minWidth: 0 }}>
            <ScoreChart history={history} predictions={predictions} accuracy={accuracy} />

            {/* Týdenní výhled: scénáře, direction label, katalyzátory */}
            <WeekSummaryPanel summary={weekSummary} />

            {/* Sekundární panely */}
            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", width: "100%" }}>
              <SentimentGaugeChart
                title="Retail Sentiment"
                dataKey="score_retail_sentiment"
                history={history}
                tooltip="Kontraindikátor! Ukazuje pozice malých retailových obchodníků. Pokud 80 % retailu shortuje EUR/USD, velcí hráči jsou pravděpodobně na opačné straně → bullish signál. Dav se mýlí — sledujeme ho obráceně."
              />
              <SentimentGaugeChart
                title="COT Bias"
                dataKey="score_cot"
                history={history}
                tooltip="Ukazuje, jak velcí institucionální hráči drží pozice na EUR a americkém dolaru. Silná net-long pozice na EUR = smart money čeká posílení EUR — jde o spolehlivý dlouhodobý sentiment indikátor."
              />
              <TechnicalPanel data={technical} />
            </div>

            <EventsPanel events={events} />
          </div>
        </div>
      )}
    </div>
  );
}

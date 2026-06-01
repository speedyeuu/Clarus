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

  // Každý endpoint má vlastní fallback — selhání jednoho neovlivní ostatní panely
  const [latestRes, historyRes, predRes, eventsRes, accuracyRes, techRes, weekRes] =
    await Promise.allSettled([
      fetchLatestScore(),
      fetchScoreHistory(30),
      fetchPredictions(),
      fetchUpcomingEvents(7),
      fetchAccuracySummary(),
      fetchTechnicalAnalysis(),
      fetchWeekSummary(),
    ]);

  if (latestRes.status === "fulfilled") today_score = latestRes.value;
  else { console.error("score/latest failed:", latestRes.reason); error_msg = "Nelze načíst skóre — běží backend?"; }

  if (historyRes.status === "fulfilled") history = historyRes.value;
  if (predRes.status === "fulfilled") predictions = predRes.value;
  if (eventsRes.status === "fulfilled") events = eventsRes.value;
  if (accuracyRes.status === "fulfilled") accuracy = accuracyRes.value;
  if (techRes.status === "fulfilled") technical = techRes.value;
  else console.error("score/technical failed:", (techRes as PromiseRejectedResult).reason);
  if (weekRes.status === "fulfilled") weekSummary = weekRes.value;
  else console.error("predictions/week-summary failed:", (weekRes as PromiseRejectedResult).reason);

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

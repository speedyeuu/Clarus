import { Suspense } from "react";
import ScoreOverview from "@/components/ScoreOverview";
import ScoreChart from "@/components/ScoreChart";
import EventsPanel from "@/components/EventsPanel";
import SentimentGaugeChart from "@/components/SentimentGaugeChart";
import TechnicalPanel from "@/components/TechnicalPanel";
import WeekSummaryPanel from "@/components/WeekSummaryPanel";
import PairSelector from "@/components/PairSelector";
import UpdatedAt from "@/components/UpdatedAt";
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

interface PageProps {
  searchParams: Promise<{ pair?: string }>;
}

export default async function DashboardPage({ searchParams }: PageProps) {
  const { pair: pairParam } = await searchParams;
  const pair = (pairParam ?? "EURUSD").toUpperCase();

  let today_score: DailyScore | null = null;
  let history: DailyScore[] = [];
  let predictions: Prediction[] = [];
  let events: UpcomingEvent[] = [];
  let accuracy: AccuracySummary = { week_avg: null, month_avg: null, week_count: 0, month_count: 0 };
  let technical = null;
  let weekSummary = null;
  let error_msg: string | null = null;

  const [latestRes, historyRes, predRes, eventsRes, accuracyRes, techRes, weekRes] =
    await Promise.allSettled([
      fetchLatestScore(pair),
      fetchScoreHistory(30, pair),
      fetchPredictions(pair),
      fetchUpcomingEvents(7),
      fetchAccuracySummary(pair),
      fetchTechnicalAnalysis(pair),
      fetchWeekSummary(pair),
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

  const pairLabel = `${pair.slice(0, 3)}/${pair.slice(3)}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

      {/* ── TOP BAR ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "16px",
        flexWrap: "wrap",
      }}>
        {/* Clarus wordmark */}
        <span style={{
          fontWeight: 700,
          fontSize: "18px",
          color: "var(--text-primary)",
          letterSpacing: "-0.02em",
          marginRight: "4px",
        }}>
          Clarus
        </span>

        {/* Oddělovač */}
        <div style={{ width: "1px", height: "20px", background: "var(--border-bright)", flexShrink: 0 }} />

        {/* Aktivní pár label */}
        <span style={{ fontSize: "12px", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          Aktivní pár:{" "}
          <strong style={{ color: "var(--text-secondary)", fontFamily: "monospace", fontSize: "13px" }}>
            {pairLabel}
          </strong>
        </span>

        {/* Pair selector tabs */}
        <Suspense fallback={null}>
          <PairSelector activePair={pair} />
        </Suspense>

        {/* Spacer — pushne zbytek doprava */}
        <div style={{ flex: 1 }} />

        {/* Live dot + aktualizováno */}
        <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
          <div style={{
            width: "7px", height: "7px",
            borderRadius: "50%",
            background: "var(--bullish)",
            animation: "pulse-glow 2s infinite",
            flexShrink: 0,
          }} />
          <UpdatedAt />
        </div>
      </div>

      {error_msg && (
        <div style={{ padding: "20px", background: "var(--bearish-dim)", color: "var(--bearish)", border: "1px solid var(--border)", borderRadius: "8px" }}>
          <strong>Chyba:</strong> {error_msg}
        </div>
      )}

      {!error_msg && !today_score && (
        <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border)", borderRadius: "8px", marginTop: "20px" }}>
          <strong>Zatím žádná data pro {pairLabel}</strong>
          <p style={{ marginTop: "10px", fontSize: "14px" }}>
            Tento měnový pár byl buď právě přidán, nebo probíhá stahování prvních dat. Skóre se objeví po dalším updatu databáze.
          </p>
        </div>
      )}

      {!error_msg && today_score && (
        <div className="dashboard-grid">

          {/* LEVÝ SLOUPEC: Score Overview + Týdenní výhled */}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <ScoreOverview score={today_score} />
            {/* Týdenní výhled přesunuto dolů pod indikátory — vyplní levý sloupec */}
            <WeekSummaryPanel summary={weekSummary} />
          </div>

          {/* PRAVÝ SLOUPEC: Graf + Sentiment gauges + Events */}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", minWidth: 0 }}>
            <ScoreChart history={history} predictions={predictions} accuracy={accuracy} />

            {/* Sentiment + COT + Technical vedle sebe */}
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

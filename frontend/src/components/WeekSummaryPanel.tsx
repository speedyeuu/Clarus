"use client";

interface ScenarioDay {
  date: string;
  events: string[];
  baseline: number;
  beat: number;
  miss: number;
  band_low: number;
  band_high: number;
  confidence: number;
  mean_reversion_applied: boolean;
}

interface WeekSummary {
  pair: string;
  current_score: number;
  current_label: string;
  direction_label: string;
  score_end_expected: number;
  score_change: number;
  change_description: string;
  scenario_days: ScenarioDay[];
  total_prediction_days: number;
}

interface Props {
  summary: WeekSummary | null;
}

function formatDate(iso: string) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("cs-CZ", { weekday: "short", day: "numeric", month: "numeric" });
}

function ScoreBar({ value, min = -10, max = 10 }: { value: number; min?: number; max?: number }) {
  const pct = ((value - min) / (max - min)) * 100;
  const color = value > 1 ? "var(--bullish)" : value < -1 ? "var(--bearish)" : "var(--text-secondary)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", width: "100%" }}>
      <div style={{ flex: 1, height: "4px", background: "var(--bg-tertiary)", borderRadius: "2px", position: "relative" }}>
        <div style={{
          position: "absolute",
          left: 0,
          width: `${Math.max(0, Math.min(100, pct))}%`,
          height: "100%",
          background: color,
          borderRadius: "2px",
          transition: "width 0.4s ease",
        }} />
      </div>
      <span style={{ fontSize: "12px", fontWeight: 700, color, minWidth: "36px", textAlign: "right" }}>
        {value > 0 ? "+" : ""}{value.toFixed(1)}
      </span>
    </div>
  );
}

function ScenarioCard({ day }: { day: ScenarioDay }) {
  const beatColor = day.beat > day.baseline ? "var(--bullish)" : "var(--bearish)";
  const missColor = day.miss < day.baseline ? "var(--bearish)" : "var(--bullish)";
  const beatChange = day.beat - day.baseline;
  const missChange = day.miss - day.baseline;

  return (
    <div style={{
      padding: "12px",
      borderRadius: "10px",
      background: "var(--bg-secondary)",
      border: "1px solid var(--border)",
      display: "flex",
      flexDirection: "column",
      gap: "8px",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", fontWeight: 600 }}>
            {formatDate(day.date)}
            {!day.mean_reversion_applied && (
              <span style={{ marginLeft: "6px", color: "#f59e0b", fontSize: "10px" }}>⚡ před key eventem</span>
            )}
          </div>
          {day.events.map((ev, i) => (
            <div key={i} style={{ fontSize: "12px", color: "var(--text-secondary)", marginTop: "2px" }}>
              📅 {ev}
            </div>
          ))}
        </div>
        <span style={{
          fontSize: "11px",
          padding: "2px 6px",
          borderRadius: "8px",
          background: "var(--bg-tertiary)",
          color: "var(--text-muted)",
        }}>
          {Math.round((day.confidence ?? 0) * 100)}% conf.
        </span>
      </div>

      {/* Scénáře */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "6px" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "10px", color: "var(--bearish)", fontWeight: 600, marginBottom: "2px" }}>
            MISS
          </div>
          <div style={{ fontSize: "14px", fontWeight: 700, color: missColor }}>
            {day.miss > 0 ? "+" : ""}{day.miss.toFixed(1)}
          </div>
          <div style={{ fontSize: "10px", color: missColor }}>
            {missChange > 0 ? "+" : ""}{missChange.toFixed(1)}
          </div>
        </div>
        <div style={{ textAlign: "center", borderLeft: "1px solid var(--border)", borderRight: "1px solid var(--border)" }}>
          <div style={{ fontSize: "10px", color: "var(--text-muted)", fontWeight: 600, marginBottom: "2px" }}>
            BASELINE
          </div>
          <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)" }}>
            {day.baseline > 0 ? "+" : ""}{day.baseline.toFixed(1)}
          </div>
          <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>
            [{day.band_low.toFixed(1)}, {day.band_high.toFixed(1)}]
          </div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "10px", color: "var(--bullish)", fontWeight: 600, marginBottom: "2px" }}>
            BEAT
          </div>
          <div style={{ fontSize: "14px", fontWeight: 700, color: beatColor }}>
            {day.beat > 0 ? "+" : ""}{day.beat.toFixed(1)}
          </div>
          <div style={{ fontSize: "10px", color: beatColor }}>
            {beatChange > 0 ? "+" : ""}{beatChange.toFixed(1)}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function WeekSummaryPanel({ summary }: Props) {
  if (!summary) {
    return (
      <div className="card" style={{ padding: "20px" }}>
        <p style={{ color: "var(--text-muted)", fontSize: "13px", textAlign: "center" }}>
          Týdenní přehled není dostupný — spusť daily update
        </p>
      </div>
    );
  }

  const changeColor = summary.score_change > 0.3 ? "var(--bullish)" :
                      summary.score_change < -0.3 ? "var(--bearish)" :
                      "var(--text-secondary)";

  return (
    <div className="card" style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3 style={{ margin: "0 0 4px 0", fontSize: "14px", fontWeight: 700, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Týdenní výhled
          </h3>
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Scénářová analýza · EUR/USD</span>
        </div>
        <span style={{
          fontSize: "12px",
          fontWeight: 700,
          padding: "4px 10px",
          borderRadius: "12px",
          background: "var(--bg-tertiary)",
          color: "var(--text-secondary)",
        }}>
          {summary.total_prediction_days}D výhled
        </span>
      </div>

      {/* Direction Banner */}
      <div style={{
        padding: "14px 16px",
        borderRadius: "10px",
        background: summary.score_end_expected > 1 ? "rgba(52,211,153,0.08)" :
                    summary.score_end_expected < -1 ? "rgba(239,68,68,0.08)" :
                    "var(--bg-tertiary)",
        border: `1px solid ${summary.score_end_expected > 1 ? "var(--bullish)" : summary.score_end_expected < -1 ? "var(--bearish)" : "var(--border)"}40`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}>
        <div>
          <div style={{ fontSize: "16px", fontWeight: 800, marginBottom: "2px" }}>
            {summary.direction_label}
          </div>
          <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
            Nyní: <strong>{summary.current_score > 0 ? "+" : ""}{summary.current_score.toFixed(1)}</strong>
            {" → "}
            Konec týdne: <strong style={{ color: changeColor }}>
              {summary.score_end_expected > 0 ? "+" : ""}{summary.score_end_expected.toFixed(1)}
            </strong>
            <span style={{ color: changeColor, marginLeft: "6px" }}>
              ({summary.change_description})
            </span>
          </div>
        </div>
      </div>

      {/* Score progression bar */}
      <div>
        <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Očekávaný pohyb skóre
        </div>
        <ScoreBar value={summary.score_end_expected} />
      </div>

      {/* Scenario Days */}
      {summary.scenario_days.length > 0 && (
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Scénáře pro klíčové dny
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {summary.scenario_days.map((day) => (
              <ScenarioCard key={day.date} day={day} />
            ))}
          </div>
        </div>
      )}

      {summary.scenario_days.length === 0 && (
        <div style={{ fontSize: "12px", color: "var(--text-muted)", textAlign: "center", padding: "8px" }}>
          Tento týden nejsou žádné klíčové události s predikovaným dopadem
        </div>
      )}
    </div>
  );
}

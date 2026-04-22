"use client";

import { INDICATOR_META, DailyScore, getScoreColor, getScoreLabel, scoreToBar } from "@/lib/types";
import InfoTooltip from "@/components/InfoTooltip";

interface Props {
  score: DailyScore;
}

function IndicatorRow({ scoreKey, value, weight }: {
  scoreKey: string;
  value: number | null;
  weight: number;
}) {
  const meta = INDICATOR_META[scoreKey];
  const bar = scoreToBar(value);
  const color = getScoreColor(value);
  const label = value !== null ? getScoreLabel(value) : "N/A";
  const displayValue = value !== null ? (value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)) : "—";

  return (
    <div style={{
      padding: "10px 0",
      borderBottom: "1px solid var(--border)",
      transition: "background 0.15s",
    }}
      className="indicator-row"
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
        {/* Left: label + weight + info */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "13px", color: "var(--text-primary)", fontWeight: 500 }}>
            {meta.label}
          </span>
          <span style={{
            fontSize: "10px", color: "var(--text-muted)",
            background: "var(--bg-elevated)", padding: "1px 5px",
            borderRadius: "3px", fontFamily: "monospace",
          }}>
            {(weight * 100).toFixed(0)}%
          </span>
          <InfoTooltip label={meta.label} text={meta.tooltip} />
        </div>

        {/* Right: value + label */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: "13px", fontWeight: 600,
            color,
          }}>
            {displayValue}
          </span>
          <span style={{ fontSize: "10px", color, opacity: 0.85 }}>
            {label}
          </span>
        </div>
      </div>

      {/* Score bar */}
      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{
            left: bar.left,
            width: bar.width,
            background: bar.color,
            boxShadow: value !== null && Math.abs(value) > 1.5 ? `0 0 8px ${bar.color}` : "none",
          }}
        />
      </div>
    </div>
  );
}

export default function ScoreOverview({ score }: Props) {

  const totalColor = getScoreColor(score.total_score);
  const totalLabel = getScoreLabel(score.total_score);
  const totalDisplay = score.total_score > 0
    ? `+${score.total_score.toFixed(2)}`
    : score.total_score.toFixed(2);

  const indicators = Object.keys(INDICATOR_META).sort(
    (a, b) => INDICATOR_META[a].order - INDICATOR_META[b].order
  );

  const weights = score.weights ?? {};

  return (
    <div className="card animate-slide-up" style={{ height: "fit-content" }}>
      {/* Header */}
      <div className="card-header">
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "2px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Score Overview
          </div>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
            {new Date(score.date).toLocaleDateString("cs-CZ", { day: "numeric", month: "long", year: "numeric" })}
          </div>
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "11px", color: "var(--text-muted)",
          padding: "3px 8px", borderRadius: "5px",
          background: "var(--bg-elevated)",
        }}>
          EUR/USD
        </div>
      </div>

      {/* Indicators list */}
      <div className="card-body" style={{ padding: "0 20px" }}>
        {indicators.map((key) => (
          <IndicatorRow
            key={key}
            scoreKey={key}
            value={(score as any)[key]}
            weight={weights[INDICATOR_META[key].weight_key] ?? 0}
          />
        ))}
      </div>

      {/* Total score footer */}
      <div style={{
        padding: "16px 20px",
        background: "var(--bg-elevated)",
        borderTop: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "2px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Total Weighted Score
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "28px", fontWeight: "700", color: totalColor,
              textShadow: Math.abs(score.total_score) > 1.5 ? `0 0 20px ${totalColor}` : "none",
            }}>
              {totalDisplay}
            </span>
            <div style={{
              display: "flex", flexDirection: "column", gap: "2px",
            }}>
              <span style={{ fontSize: "16px" }}>
                {score.total_score >= 2 ? "🟢" : score.total_score >= 0.33 ? "🟡" : score.total_score > -0.33 ? "⚪" : score.total_score > -2 ? "🟠" : "🔴"}
              </span>
            </div>
          </div>
        </div>
        <div style={{
          textAlign: "right",
        }}>
          <div style={{
            fontSize: "15px", fontWeight: "600", color: totalColor,
          }}>
            {totalLabel}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>
            Scale: −3 to +3
          </div>
        </div>
      </div>
    </div>
  );
}

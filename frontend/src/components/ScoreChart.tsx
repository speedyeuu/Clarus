"use client";

import { useEffect, useRef } from "react";
import { DailyScore, Prediction, getScoreColor } from "@/lib/types";

interface ChartPoint {
  date: string;
  value: number;
  isPrediction?: boolean;
  low?: number;
  high?: number;
}

interface Props {
  history: DailyScore[];
  predictions: Prediction[];
}

export default function ScoreChart({ history, predictions }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Připraví data pro chart
  const historyPoints: ChartPoint[] = history.map((d) => ({
    date: d.date,
    value: d.total_score,
  }));

  const predictionPoints: ChartPoint[] = predictions.map((p) => ({
    date: p.prediction_date,
    value: p.predicted_score_mid,
    isPrediction: true,
    low: p.predicted_score_low,
    high: p.predicted_score_high,
  }));

  const allPoints = [...historyPoints, ...predictionPoints];
  const todayScore = history[history.length - 1]?.total_score ?? 0;
  const yesterdayScore = history[history.length - 2]?.total_score ?? 0;
  const change24h = todayScore - yesterdayScore;

  // SVG chart dimensions
  const W = 800;
  const H = 220;
  const PAD = { top: 20, right: 20, bottom: 30, left: 40 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  // Y scale: -3 to +3
  const yMin = -3, yMax = 3;
  const yScale = (v: number) => PAD.top + ((yMax - v) / (yMax - yMin)) * innerH;

  // X scale
  const xScale = (i: number, total: number) => PAD.left + (i / (total - 1)) * innerW;

  // Build SVG paths
  const histLen = historyPoints.length;
  const predLen = predictionPoints.length;
  const total = allPoints.length;

  const histPath = historyPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(i, total)} ${yScale(p.value)}`
  ).join(" ");

  const predPath = predictionPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(histLen - 1 + i, total)} ${yScale(p.value)}`
  ).join(" ");

  // Prediction band area
  const bandTop = predictionPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(histLen - 1 + i, total)} ${yScale(p.high ?? p.value + 0.5)}`
  ).join(" ");
  const bandBot = [...predictionPoints].reverse().map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(histLen - 1 + (predLen - 1 - i), total)} ${yScale(p.low ?? p.value - 0.5)}`
  ).join(" ");
  const bandPath = `${bandTop} ${bandBot} Z`;

  // Zero line y
  const zeroY = yScale(0);

  // Last point for glow dot
  const lastHistX = xScale(histLen - 1, total);
  const lastHistY = yScale(todayScore);

  const changeColor = change24h > 0 ? "var(--bullish)" : change24h < 0 ? "var(--bearish)" : "var(--neutral)";

  return (
    <div className="card animate-slide-up" style={{ animationDelay: "0.1s" }}>
      <div className="card-header">
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "2px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Score History
          </div>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)", display: "flex", gap: "12px", alignItems: "center" }}>
            <span>Posledních 30 dní + 7 dní predikce</span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {/* 24h change badge */}
          <div style={{
            display: "flex", alignItems: "center", gap: "5px",
            padding: "4px 10px", borderRadius: "6px",
            background: change24h > 0 ? "var(--bullish-dim)" : change24h < 0 ? "var(--bearish-dim)" : "var(--neutral-dim)",
          }}>
            <span style={{ fontSize: "14px" }}>{change24h > 0 ? "↑" : change24h < 0 ? "↓" : "→"}</span>
            <span style={{ fontFamily: "monospace", fontSize: "13px", fontWeight: 600, color: changeColor }}>
              {change24h > 0 ? "+" : ""}{change24h.toFixed(2)}
            </span>
            <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>24h</span>
          </div>

          {/* Time range buttons */}
          <div style={{ display: "flex", gap: "4px" }}>
            {["1W", "1M", "3M"].map((range) => (
              <button
                key={range}
                disabled={range === "3M"}
                style={{
                  padding: "3px 10px",
                  borderRadius: "5px",
                  border: "1px solid var(--border)",
                  background: range === "1M" ? "var(--bg-elevated)" : "transparent",
                  color: range === "3M" ? "var(--text-muted)" : range === "1M" ? "var(--text-primary)" : "var(--text-secondary)",
                  fontSize: "12px", fontWeight: 500,
                  cursor: range === "3M" ? "not-allowed" : "pointer",
                  opacity: range === "3M" ? 0.4 : 1,
                  transition: "all 0.15s",
                }}
              >
                {range}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card-body" style={{ padding: "16px 20px 12px" }}>
        {/* Legend */}
        <div style={{ display: "flex", gap: "20px", marginBottom: "12px", fontSize: "11px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ width: "20px", height: "2px", background: "var(--prediction)", borderRadius: "1px" }} />
            <span style={{ color: "var(--text-secondary)" }}>Historické skóre</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ width: "20px", height: "2px", background: "var(--prediction)", borderRadius: "1px", borderTop: "2px dashed var(--prediction)", background: "transparent" }} />
            <span style={{ color: "var(--text-secondary)" }}>Predikce (7 dní)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ width: "14px", height: "8px", background: "rgba(244,63,94,0.15)", borderRadius: "2px" }} />
            <span style={{ color: "var(--text-secondary)" }}>Predikční zóna</span>
          </div>
        </div>

        {/* SVG Chart */}
        <div ref={containerRef} style={{ width: "100%", overflowX: "auto" }}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            style={{ width: "100%", minWidth: "400px", height: "auto", display: "block" }}
          >
            <defs>
              <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--prediction)" stopOpacity="0.15" />
                <stop offset="100%" stopColor="var(--prediction)" stopOpacity="0" />
              </linearGradient>
              <filter id="glow">
                <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                <feMerge><feMergeNode in="coloredBlur" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
            </defs>

            {/* Y-axis grid lines */}
            {[-3, -2, -1, 0, 1, 2, 3].map((v) => (
              <g key={v}>
                <line
                  x1={PAD.left} y1={yScale(v)} x2={W - PAD.right} y2={yScale(v)}
                  stroke={v === 0 ? "var(--border-bright)" : "var(--border)"}
                  strokeWidth={v === 0 ? 1.5 : 0.5}
                  strokeDasharray={v === 0 ? "none" : "3,4"}
                />
                <text
                  x={PAD.left - 6} y={yScale(v) + 4}
                  textAnchor="end" fill="var(--text-muted)" fontSize="10"
                  fontFamily="monospace"
                >
                  {v > 0 ? `+${v}` : v}
                </text>
              </g>
            ))}

            {/* Prediction band */}
            {predictionPoints.length > 0 && (
              <path d={bandPath} fill="rgba(244,63,94,0.08)" stroke="none" />
            )}

            {/* History area fill */}
            {historyPoints.length > 1 && (
              <path
                d={`${histPath} L ${xScale(histLen - 1, total)} ${H - PAD.bottom} L ${xScale(0, total)} ${H - PAD.bottom} Z`}
                fill="url(#histGrad)"
              />
            )}

            {/* History line */}
            {historyPoints.length > 1 && (
              <path d={histPath} fill="none" stroke="var(--prediction)" strokeWidth="2" strokeLinecap="round" />
            )}

            {/* Prediction line (dashed) */}
            {predictionPoints.length > 0 && (
              <path
                d={predPath}
                fill="none"
                stroke="var(--prediction)"
                strokeWidth="1.5"
                strokeDasharray="5,4"
                strokeLinecap="round"
                opacity="0.7"
              />
            )}

            {/* Today dot with glow */}
            {historyPoints.length > 0 && (
              <>
                <circle cx={lastHistX} cy={lastHistY} r="6" fill="var(--bg-card)" stroke="var(--prediction)" strokeWidth="2" filter="url(#glow)" />
                <circle cx={lastHistX} cy={lastHistY} r="3" fill="var(--prediction)" />
              </>
            )}

            {/* Today separator line */}
            {historyPoints.length > 0 && predictionPoints.length > 0 && (
              <line
                x1={lastHistX} y1={PAD.top}
                x2={lastHistX} y2={H - PAD.bottom}
                stroke="var(--border-bright)"
                strokeWidth="1"
                strokeDasharray="3,3"
              />
            )}

            {/* X-axis dates (every 7 days) */}
            {allPoints.filter((_, i) => i % 7 === 0).map((p, i) => {
              const origI = allPoints.indexOf(p);
              return (
                <text
                  key={p.date}
                  x={xScale(origI, total)}
                  y={H - PAD.bottom + 16}
                  textAnchor="middle"
                  fill="var(--text-muted)"
                  fontSize="9"
                >
                  {new Date(p.date).toLocaleDateString("cs-CZ", { day: "numeric", month: "numeric" })}
                </text>
              );
            })}
          </svg>
        </div>
      </div>
    </div>
  );
}

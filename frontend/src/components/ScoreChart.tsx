"use client";

import { useEffect, useRef, useState } from "react";
import { DailyScore, Prediction, AccuracySummary, getScoreColor } from "@/lib/types";

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
  accuracy?: AccuracySummary;
}

export default function ScoreChart({ history, predictions, accuracy }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState<"1W" | "1M">("1M");

  const daysToSlice = range === "1W" ? 7 : 30;
  const filteredHistory = history.slice(-daysToSlice);

  // Připraví data pro chart
  const historyPoints: ChartPoint[] = filteredHistory.map((d) => ({
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

  const lastHistPoint = historyPoints[historyPoints.length - 1];

  // Odstraníme předpovědi, které jsou starší nebo rovny poslednímu historickému bodu (zabrání překryvu)
  const filteredPredictionPoints = lastHistPoint
    ? predictionPoints.filter((p) => p.date > lastHistPoint.date)
    : predictionPoints;

  // Pro vykreslení cesty (čáry a pásma) napojíme predikci přímo na poslední historický bod
  const predictionPathPoints = lastHistPoint
    ? [{ ...lastHistPoint, high: lastHistPoint.value, low: lastHistPoint.value, isPrediction: true }, ...filteredPredictionPoints]
    : filteredPredictionPoints;

  const allPoints = [...historyPoints, ...filteredPredictionPoints];
  const todayScore = history[history.length - 1]?.total_score ?? 0;
  const yesterdayScore = history[history.length - 2]?.total_score ?? 0;
  const change24h = todayScore - yesterdayScore;

  // SVG chart dimensions
  const W = 800;
  const H = range === "1M" ? 310 : 280;
  const PAD = { top: 20, right: 20, bottom: range === "1M" ? 55 : 30, left: 40 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  // Škála Y je fixní od -11 do +11, což dává perfektní zobrazení celého rozsahu -10 až +10 bez ořezání okrajů zobrazení
  const yMin = -11.0;
  const yMax = 11.0;

  const yScale = (v: number) => PAD.top + ((yMax - v) / (yMax - yMin)) * innerH;

  // Značky na ose Y po 1 jednotce
  const yTicks = Array.from({ length: 21 }, (_, i) => i - 10);

  // X scale — používáme reálné datumy, ne indexy, aby mezery v datech byly proporcionálně správné
  const allDates = allPoints.map(p => new Date(p.date).getTime());
  const minDate = Math.min(...allDates);
  const maxDate = Math.max(...allDates);
  const dateRange = maxDate - minDate || 1;
  const xScale = (_i: number, _total: number, date?: string) => {
    if (!date) return PAD.left + (_i / Math.max(1, _total - 1)) * innerW;
    return PAD.left + ((new Date(date).getTime() - minDate) / dateRange) * innerW;
  };

  // Build SVG paths
  const histLen = historyPoints.length;
  const predLen = filteredPredictionPoints.length;
  const total = allPoints.length;

  const histPath = historyPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(i, total, p.date)} ${yScale(p.value)}`
  ).join(" ");

  const predPath = predictionPathPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(0, 0, p.date)} ${yScale(p.value)}`
  ).join(" ");

  // Prediction band area
  const bandTop = predictionPathPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(0, 0, p.date)} ${yScale(p.high ?? p.value + 0.5)}`
  ).join(" ");
  const bandBot = [...predictionPathPoints].reverse().map((p) =>
    `L ${xScale(0, 0, p.date)} ${yScale(p.low ?? p.value - 0.5)}`
  ).join(" ");
  const bandPath = `${bandTop} ${bandBot} Z`;

  // Zero line y
  const zeroY = yScale(0);

  // Last point for glow dot (already defined above as lastHistPoint)
  const lastHistX = lastHistPoint ? xScale(0, 0, lastHistPoint.date) : PAD.left;
  const lastHistY = yScale(todayScore);

  const changeColor = change24h > 0 ? "var(--bullish)" : change24h < 0 ? "var(--bearish)" : "var(--neutral)";

  const handleDownloadXlsx = async () => {
    const { utils, write } = await import("xlsx");
    const pairName = history.length > 0 && history[0].pair ? history[0].pair : "EUR_USD";

    // Připrav data jako pole objektů
    const rows = [
      ["Clarus Trading Software – Export dat pro pár: " + pairName],
      [],
      ["Datum", "Overall Score"],
      ...history.map((d) => {
        const [year, month, day] = d.date.split("-");
        return [`${day}.${month}.${year}`, d.total_score];
      }),
    ];

    const wb = utils.book_new();
    const ws = utils.aoa_to_sheet(rows);

    // Nastav šířky sloupců: Datum = 15 znaků, Score = 16 znaků
    ws["!cols"] = [{ wch: 15 }, { wch: 16 }];

    utils.book_append_sheet(wb, ws, pairName.replace("/", "_"));

    const buf = write(wb, { bookType: "xlsx", type: "array" });
    const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `clarus_${pairName.replace("/", "_")}_export.xlsx`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };


  return (
    <div className="card animate-slide-up" style={{ animationDelay: "0.1s" }}>
      <div className="card-header">
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "2px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Score History
          </div>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: "2px" }}>
            <span>Posledních 30 dní + 7 dní predikce</span>
            <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ opacity: 0.7 }}>Přesnost predikcí:</span>
              {accuracy && (accuracy.week_count >= 3 || accuracy.month_count >= 3) ? (
                <>
                  {accuracy.week_count >= 3 && (
                    <span style={{
                      color: accuracy.week_avg! >= 0.75 ? "var(--bullish)" : accuracy.week_avg! >= 0.5 ? "var(--text-secondary)" : "var(--bearish)",
                      fontWeight: 600, fontFamily: "monospace",
                    }}>
                      7d {Math.round(accuracy.week_avg! * 100)}%
                    </span>
                  )}
                  {accuracy.week_count >= 3 && accuracy.month_count >= 3 && <span style={{ opacity: 0.4 }}>|</span>}
                  {accuracy.month_count >= 3 && (
                    <span style={{
                      color: accuracy.month_avg! >= 0.75 ? "var(--bullish)" : accuracy.month_avg! >= 0.5 ? "var(--text-secondary)" : "var(--bearish)",
                      fontWeight: 600, fontFamily: "monospace",
                    }}>
                      30d {Math.round(accuracy.month_avg! * 100)}%
                    </span>
                  )}
                </>
              ) : (
                <span style={{ opacity: 0.5, fontStyle: "italic" }}>Nedostatek dat</span>
              )}
            </span>
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
            {["1W", "1M"].map((r) => (
              <button
                key={r}
                onClick={() => setRange(r as "1W" | "1M")}
                style={{
                  padding: "3px 10px",
                  borderRadius: "5px",
                  border: "1px solid var(--border)",
                  background: range === r ? "var(--bg-elevated)" : "transparent",
                  color: range === r ? "var(--text-primary)" : "var(--text-secondary)",
                  fontSize: "12px", fontWeight: 500,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                {r}
              </button>
            ))}
            <button
              onClick={handleDownloadXlsx}
              title="Stáhnout za 1 měsíc (XLSX)"
              style={{
                display: "flex", alignItems: "center", gap: "6px",
                marginLeft: "8px", padding: "3px 10px",
                borderRadius: "5px", border: "1px solid var(--border)",
                background: "rgba(16, 185, 129, 0.1)", // mírně nazelenalé
                color: "var(--bullish)",
                fontSize: "12px", fontWeight: 600, cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
              .XLSX
            </button>
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
            <div style={{ width: "20px", height: "2px", borderRadius: "1px", borderTop: "2px dashed var(--prediction)", background: "transparent" }} />
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
            {yTicks.map((v) => (
              <g key={v}>
                <line
                  x1={PAD.left} y1={yScale(v)} x2={W - PAD.right} y2={yScale(v)}
                  stroke={v === 0 ? "var(--border-bright)" : "var(--border)"}
                  strokeWidth={v === 0 ? 1.5 : 0.5}
                  strokeDasharray={v === 0 ? "none" : "3,4"}
                  opacity={v % 5 === 0 ? 0.8 : 0.25} // Mírně tlumíme čáry, které nejsou násobky 5
                />
                <text
                  x={PAD.left - 6} y={yScale(v) + 3}
                  textAnchor="end" fill="var(--text-muted)" fontSize="8"
                  fontFamily="monospace"
                  opacity={v % 2 === 0 ? 1.0 : 0.5} // Lichá čísla jsou o něco světlejší, aby to nepůsobilo přeplněně
                >
                  {v > 0 ? `+${v}` : v}
                </text>
              </g>
            ))}

            {/* Prediction band */}
            {filteredPredictionPoints.length > 0 && (
              <path d={bandPath} fill="rgba(244,63,94,0.08)" stroke="none" />
            )}

            {/* History area fill */}
            {historyPoints.length > 1 && (
              <path
                d={`${histPath} L ${xScale(0, 0, historyPoints[histLen-1].date)} ${H - PAD.bottom} L ${xScale(0, 0, historyPoints[0].date)} ${H - PAD.bottom} Z`}
                fill="url(#histGrad)"
              />
            )}

            {/* History line */}
            {historyPoints.length > 1 && (
              <path d={histPath} fill="none" stroke="var(--prediction)" strokeWidth="2" strokeLinecap="round" />
            )}

            {/* Prediction line (dashed) */}
            {filteredPredictionPoints.length > 0 && (
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
            {historyPoints.length > 0 && filteredPredictionPoints.length > 0 && (
              <line
                x1={lastHistX} y1={PAD.top}
                x2={lastHistX} y2={H - PAD.bottom}
                stroke="var(--border-bright)"
                strokeWidth="1"
                strokeDasharray="3,3"
              />
            )}

            {/* X-axis vertical grid lines — každý den */}
            {allPoints.map((p) => (
              <line
                key={`grid-v-${p.date}`}
                x1={xScale(0, 0, p.date)} y1={PAD.top}
                x2={xScale(0, 0, p.date)} y2={H - PAD.bottom}
                stroke={p.isPrediction ? "rgba(244,63,94,0.15)" : "var(--border)"}
                strokeWidth="0.5"
                strokeDasharray="2,4"
                opacity="0.5"
              />
            ))}

            {/* X-axis dates — každý den, popisky pootočené pro 1M view */}
            {allPoints.map((p, i) => {
              const x = xScale(0, 0, p.date);
              const label = new Date(p.date).toLocaleDateString("cs-CZ", { day: "numeric", month: "numeric" });
              // V 1M view pootočíme o -45° aby se nepřekrývaly
              const rotate = range === "1M" ? `rotate(-45, ${x}, ${H - PAD.bottom + 10})` : "";
              const yOffset = range === "1M" ? H - PAD.bottom + 14 : H - PAD.bottom + 16;
              return (
                <text
                  key={p.date}
                  x={x}
                  y={yOffset}
                  textAnchor={range === "1M" ? "end" : "middle"}
                  fill={p.isPrediction ? "rgba(244,63,94,0.6)" : "var(--text-muted)"}
                  fontSize={range === "1M" ? "7.5" : "9"}
                  transform={rotate}
                >
                  {label}
                </text>
              );
            })}
          </svg>
        </div>
      </div>
    </div>
  );
}

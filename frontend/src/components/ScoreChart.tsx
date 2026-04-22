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

  // Extrémně dynamická Y osa pro maximální roztažení rozdílů
  const allValues = allPoints.flatMap((p) => [p.value, p.low ?? p.value, p.high ?? p.value]);
  const minVal = allValues.length > 0 ? Math.min(...allValues) : -3;
  const maxVal = allValues.length > 0 ? Math.max(...allValues) : 3;

  const valueRange = maxVal > minVal ? maxVal - minVal : 1;
  // Snížíme padding jen na 5 % pro vizuální hezkost rámečku (aby kolečko na konci nebylo zaříznuté)
  const yMin = minVal - valueRange * 0.05;
  const yMax = maxVal + valueRange * 0.05;

  const yScale = (v: number) => PAD.top + ((yMax - v) / (yMax - yMin)) * innerH;

  // Výpočet hezkých značek na ose Y, podporující i malá desetinná čísla
  const tickRange = yMax - yMin;
  const roughStep = tickRange / 5;
  const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep || 1)));
  const normalizedStep = roughStep / magnitude;
  
  let niceStep = 1;
  if (normalizedStep < 1.5) niceStep = 1;
  else if (normalizedStep < 3) niceStep = 2;
  else if (normalizedStep < 7.5) niceStep = 5;
  else niceStep = 10;
  niceStep *= magnitude;

  const yTicks: number[] = [];
  const startTick = Math.ceil(yMin / niceStep) * niceStep;
  for (let i = startTick; i <= yMax; i += niceStep) {
    yTicks.push(Number(i.toFixed(6))); // toFixed eliminuje plovoucí odchylky
  }
  // Vynutíme 0
  if (!yTicks.some(t => Math.abs(t) < 1e-6) && yMin <= 0 && yMax >= 0) {
    yTicks.push(0);
    yTicks.sort((a, b) => a - b);
  }

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
  const predLen = predictionPoints.length;
  const total = allPoints.length;

  const histPath = historyPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(i, total, p.date)} ${yScale(p.value)}`
  ).join(" ");

  const predPath = predictionPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(0, 0, p.date)} ${yScale(p.value)}`
  ).join(" ");

  // Prediction band area
  const bandTop = predictionPoints.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(0, 0, p.date)} ${yScale(p.high ?? p.value + 0.5)}`
  ).join(" ");
  const bandBot = [...predictionPoints].reverse().map((p) =>
    `L ${xScale(0, 0, p.date)} ${yScale(p.low ?? p.value - 0.5)}`
  ).join(" ");
  const bandPath = `${bandTop} ${bandBot.replace("L", "M")} Z`;

  // Zero line y
  const zeroY = yScale(0);

  // Last point for glow dot
  const lastHistPoint = historyPoints[histLen - 1];
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
                />
                <text
                  x={PAD.left - 6} y={yScale(v) + 4}
                  textAnchor="end" fill="var(--text-muted)" fontSize="10"
                  fontFamily="monospace"
                >
                  {v > 0 ? `+${Number(v.toFixed(2))}` : Number(v.toFixed(2))}
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
                d={`${histPath} L ${xScale(0, 0, historyPoints[histLen-1].date)} ${H - PAD.bottom} L ${xScale(0, 0, historyPoints[0].date)} ${H - PAD.bottom} Z`}
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

            {/* X-axis dates — zobraz každých 7 dní dle reálného datumu */}
            {allPoints.filter((_, i) => i % 7 === 0).map((p) => (
              <text
                key={p.date}
                x={xScale(0, 0, p.date)}
                y={H - PAD.bottom + 16}
                textAnchor="middle"
                fill="var(--text-muted)"
                fontSize="9"
              >
                {new Date(p.date).toLocaleDateString("cs-CZ", { day: "numeric", month: "numeric" })}
              </text>
            ))}
          </svg>
        </div>
      </div>
    </div>
  );
}

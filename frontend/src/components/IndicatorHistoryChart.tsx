"use client";

import { useRef } from "react";
import { DailyScore } from "@/lib/types";
import InfoTooltip from "@/components/InfoTooltip";

interface Props {
  title: string;
  history: DailyScore[];
  dataKey: keyof DailyScore;
  tooltip?: string;
}

export default function IndicatorHistoryChart({ title, history, dataKey, tooltip }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Získáme všechny body (ignorujeme null a mapujeme na 0, i když by neměly být null)
  const points = history.map((h) => ({
    date: h.date,
    value: typeof h[dataKey] === "number" ? (h[dataKey] as number) : 0,
  }));

  const W = 400;
  const H = 140; // Malý kompaktní graf
  const PAD = { top: 20, right: 15, bottom: 20, left: 25 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const total = points.length;
  // X scale
  const xScale = (i: number) => PAD.left + (i / Math.max(1, total - 1)) * innerW;

  // Y osa je pro dílčí data standardně -3 až +3
  const yMin = -3;
  const yMax = 3;
  
  const yScale = (v: number) => PAD.top + ((yMax - v) / (yMax - yMin)) * innerH;

  const pathD = points.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(p.value)}`
  ).join(" ");
  
  const zeroY = yScale(0);

  const currentValue = points.length > 0 ? points[points.length - 1].value : 0;
  const isBullish = currentValue > 0;
  // Pokud je přesně 0, dáme neutral (šedou)
  const currentColor = currentValue > 0 ? "var(--bullish)" : currentValue < 0 ? "var(--bearish)" : "var(--neutral)";
  const currentDimColor = currentValue > 0 ? "var(--bullish-dim)" : currentValue < 0 ? "var(--bearish-dim)" : "var(--neutral-dim)";

  return (
    <div className="card animate-slide-up" style={{ padding: "16px", flex: 1, minWidth: "250px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px", alignItems: "flex-start" }}>
        <div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {title}
            </div>
            {tooltip && <InfoTooltip label={title} text={tooltip} />}
          </div>
        </div>
        <div style={{
          fontSize: "14px", fontWeight: 600, fontFamily: "monospace", color: currentColor,
          background: currentDimColor,
          padding: "4px 8px", borderRadius: "4px"
        }}>
          {currentValue > 0 ? "+" : ""}{currentValue.toFixed(2)}
        </div>
      </div>

      <div ref={containerRef} style={{ width: "100%", overflowX: "auto" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
          {/* Y Axis Grid */}
          {[-3, -2, -1, 0, 1, 2, 3].map(v => (
             <g key={v}>
                 <line x1={PAD.left} y1={yScale(v)} x2={W - PAD.right} y2={yScale(v)} stroke={v === 0 ? "var(--border-bright)" : "var(--border)"} strokeWidth={v === 0 ? 1 : 0.5} strokeDasharray={v === 0 ? "none" : "2,2"} opacity={v === 0 ? 1 : 0.5} />
                 <text x={PAD.left - 5} y={yScale(v) + 3} textAnchor="end" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">
                   {v > 0 ? `+${v}` : v}
                 </text>
             </g>
          ))}

          {/* Area Fill */}
          {points.length > 1 && (
             <path d={`${pathD} L ${xScale(total - 1)} ${zeroY} L ${xScale(0)} ${zeroY} Z`} fill={currentColor} opacity="0.1" />
          )}

          {/* Line */}
          {points.length > 1 && (
             <path d={pathD} fill="none" stroke={currentColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          )}

          {/* Last Dot */}
          {points.length > 0 && (
             <circle cx={xScale(total - 1)} cy={yScale(currentValue)} r="4" fill="var(--bg-card)" stroke={currentColor} strokeWidth="2" filter="url(#glow)" />
          )}
          {points.length > 0 && (
             <circle cx={xScale(total - 1)} cy={yScale(currentValue)} r="2" fill={currentColor} />
          )}
        </svg>
      </div>
    </div>
  );
}

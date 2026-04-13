"use client";

import { UpcomingEvent } from "@/lib/types";

interface Props {
  events: UpcomingEvent[];
}

const DAY_NAMES = ["Ne", "Po", "Út", "St", "Čt", "Pá", "So"];
const MONTH_NAMES = ["led", "úno", "bře", "dub", "kvě", "čer", "čvc", "srp", "zář", "říj", "lis", "pro"];

function formatEventDate(dateStr: string) {
  const d = new Date(dateStr);
  return `${DAY_NAMES[d.getDay()]} ${d.getDate()}. ${MONTH_NAMES[d.getMonth()]}`;
}

function groupByDate(events: UpcomingEvent[]): Record<string, UpcomingEvent[]> {
  return events.reduce((acc, ev) => {
    if (!acc[ev.event_date]) acc[ev.event_date] = [];
    acc[ev.event_date].push(ev);
    return acc;
  }, {} as Record<string, UpcomingEvent[]>);
}

export default function EventsPanel({ events }: Props) {
  const grouped = groupByDate(events);
  const sortedDates = Object.keys(grouped).sort();

  return (
    <div className="card animate-slide-up" style={{ animationDelay: "0.15s" }}>
      <div className="card-header">
        <div>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "2px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Upcoming Events
          </div>
          <div style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
            Příštích 7 dní
          </div>
        </div>
        <span style={{
          fontSize: "11px", color: "var(--text-muted)",
          padding: "3px 8px", borderRadius: "5px",
          background: "var(--bg-elevated)",
        }}>
          {events.length} událostí
        </span>
      </div>

      <div style={{ maxHeight: "380px", overflowY: "auto" }}>
        {sortedDates.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            Žádné nadcházející události
          </div>
        ) : (
          sortedDates.map((date) => (
            <div key={date}>
              {/* Date separator */}
              <div style={{
                padding: "6px 20px",
                background: "var(--bg-elevated)",
                borderBottom: "1px solid var(--border)",
                fontSize: "11px",
                color: "var(--text-secondary)",
                fontWeight: 600,
                letterSpacing: "0.03em",
              }}>
                📅 {formatEventDate(date)}
              </div>

              {/* Events for this date */}
              {grouped[date].map((ev, idx) => (
                <div
                  key={ev.id}
                  style={{
                    padding: "12px 20px",
                    borderBottom: idx < grouped[date].length - 1 ? "1px solid var(--border)" : "none",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "12px",
                    transition: "background 0.15s",
                  }}
                  className="event-row"
                >
                  {/* Impact dot */}
                  <div style={{ paddingTop: "3px" }}>
                    <div className={`impact-dot ${ev.impact?.toLowerCase()}`} />
                  </div>

                  {/* Event info */}
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                      {/* Country flag */}
                      <span style={{
                        fontSize: "10px", fontWeight: 600,
                        padding: "1px 5px", borderRadius: "3px",
                        background: ev.country === "USD" ? "rgba(59,130,246,0.15)" : "rgba(34,211,160,0.12)",
                        color: ev.country === "USD" ? "#60a5fa" : "var(--bullish)",
                      }}>
                        {ev.country}
                      </span>
                      <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary)" }}>
                        {ev.title}
                      </span>
                    </div>

                    <div style={{ display: "flex", gap: "16px", fontSize: "11px", color: "var(--text-muted)" }}>
                      {ev.event_time && (
                        <span>🕐 {ev.event_time} UTC</span>
                      )}
                      {ev.forecast && (
                        <span>Forecast: <span style={{ color: "var(--text-secondary)" }}>{ev.forecast}</span></span>
                      )}
                      {ev.previous && (
                        <span>Prev: <span style={{ color: "var(--text-secondary)" }}>{ev.previous}</span></span>
                      )}
                    </div>
                  </div>

                  {/* Polymarket / EURIBOR probability */}
                  {(ev.polymarket_yes_prob !== null || ev.euribor_signal !== null) && (
                    <div style={{ textAlign: "right", flexShrink: 0 }}>
                      {ev.polymarket_yes_prob !== null && (
                        <div style={{
                          fontSize: "11px", color: "var(--prediction)",
                          background: "var(--prediction-dim)",
                          padding: "2px 7px", borderRadius: "4px",
                          fontWeight: 600,
                        }}>
                          PM {(ev.polymarket_yes_prob * 100).toFixed(0)}%
                        </div>
                      )}
                      {ev.euribor_signal !== null && (
                        <div style={{
                          fontSize: "11px", color: "var(--bullish)",
                          background: "var(--bullish-dim)",
                          padding: "2px 7px", borderRadius: "4px",
                          fontWeight: 600, marginTop: "2px",
                        }}>
                          OIS {(ev.euribor_signal * 100).toFixed(0)}%
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

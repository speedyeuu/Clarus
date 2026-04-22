import type { DailyScore, Prediction, UpcomingEvent, AutoresearchLog, AccuracySummary } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    next: { revalidate: 60 }, // ISR: revalidate každých 60s
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export async function fetchLatestScore() {
  return apiGet<DailyScore>("/api/score/latest");
}

export async function fetchScoreHistory(days = 30) {
  return apiGet<DailyScore[]>(`/api/score/history?days=${days}`);
}

export async function fetchPredictions() {
  return apiGet<Prediction[]>("/api/predictions/");
}

export async function fetchPredictionAccuracy(days = 30) {
  return apiGet<Record<string, number>>(`/api/predictions/accuracy?days=${days}`);
}

export async function fetchAccuracySummary(): Promise<AccuracySummary> {
  try {
    return await apiGet<AccuracySummary>("/api/predictions/accuracy-summary");
  } catch {
    return { week_avg: null, month_avg: null, week_count: 0, month_count: 0 };
  }
}

export async function fetchUpcomingEvents(days = 7) {
  return apiGet<UpcomingEvent[]>(`/api/events/upcoming?days=${days}`);
}

export async function fetchAutoresearchLog() {
  return apiGet<AutoresearchLog[]>("/api/autoresearch/log");
}

export async function fetchPendingProposals() {
  return apiGet<AutoresearchLog[]>("/api/autoresearch/pending");
}

export async function approveProposal(logId: string, approved: boolean) {
  const res = await fetch(`${API_BASE}/api/autoresearch/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ log_id: logId, approved }),
  });
  if (!res.ok) throw new Error("Approve failed");
  return res.json();
}

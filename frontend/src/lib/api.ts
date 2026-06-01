import type { DailyScore, Prediction, UpcomingEvent, AccuracySummary } from "./types";

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

export interface TechnicalData {
  pair: string;
  close: number;
  rsi: number;
  ema20: number;
  ema50: number;
  adx: number;
  dist_from_ema20_pct: number;
  dist_from_ema50_pct: number;
  ema_cross_pct: number;
  ema20_above_ema50: boolean;
  price_above_ema50: boolean;
  total_score: number;
  entry_signal: {
    signal: string;
    label: string;
    color: string;
    description: string;
  };
  rsi_zone: "oversold" | "overbought" | "normal";
}

export async function fetchTechnicalAnalysis(): Promise<TechnicalData | null> {
  try {
    return await apiGet<TechnicalData>("/api/score/technical");
  } catch {
    return null;
  }
}

export interface WeekSummary {
  pair: string;
  current_score: number;
  current_label: string;
  direction_label: string;
  score_end_expected: number;
  score_change: number;
  change_description: string;
  scenario_days: {
    date: string;
    events: string[];
    baseline: number;
    beat: number;
    miss: number;
    band_low: number;
    band_high: number;
    confidence: number;
    mean_reversion_applied: boolean;
  }[];
  total_prediction_days: number;
}

export async function fetchWeekSummary(): Promise<WeekSummary | null> {
  try {
    return await apiGet<WeekSummary>("/api/predictions/week-summary");
  } catch {
    return null;
  }
}

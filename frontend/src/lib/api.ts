const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    next: { revalidate: 60 }, // ISR: revalidate každých 60s
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export async function fetchLatestScore() {
  return apiGet("/api/score/latest");
}

export async function fetchScoreHistory(days = 30) {
  return apiGet(`/api/score/history?days=${days}`);
}

export async function fetchPredictions() {
  return apiGet("/api/predictions/");
}

export async function fetchPredictionAccuracy(days = 30) {
  return apiGet(`/api/predictions/accuracy?days=${days}`);
}

export async function fetchUpcomingEvents(days = 7) {
  return apiGet(`/api/events/upcoming?days=${days}`);
}

export async function fetchAutoresearchLog() {
  return apiGet("/api/autoresearch/log");
}

export async function fetchPendingProposals() {
  return apiGet("/api/autoresearch/pending");
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

/**
 * Server komponent — fetchuje datum poslední aktualizace z backendu.
 * Zobrazuje se v hlavičce vedle EUR/USD.
 */
export default async function UpdatedAt() {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${API_BASE}/api/score/latest`, {
      next: { revalidate: 300 }, // revalidate každých 5 min
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.date) return null;

    const formatted = new Date(data.date).toLocaleDateString("cs-CZ", {
      day: "numeric",
      month: "numeric",
      year: "numeric",
    });

    return (
      <span style={{
        fontSize: "11px",
        color: "var(--text-muted)",
        whiteSpace: "nowrap",
      }}>
        Aktualizováno k {formatted}
      </span>
    );
  } catch {
    return null;
  }
}

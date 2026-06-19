/**
 * Server komponent — fetchuje datum poslední aktualizace z backendu.
 * Zobrazuje se v hlavičce vedle EUR/USD.
 * Barevně indikuje stáří dat: zelená (dnes), oranžová (1 den), červená (2+ dní).
 */
export default async function UpdatedAt({ pair }: { pair: string }) {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${API_BASE}/api/score/latest?pair=${pair}`, {
      headers: {
        "ngrok-skip-browser-warning": "true",
      },
      next: { revalidate: 300 }, // revalidate každých 5 min
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.date) return null;

    // Parsujeme datum jako lokální datum (ISO string YYYY-MM-DD bez timezone)
    const [year, month, day] = data.date.split("T")[0].split("-").map(Number);
    const dataDate = new Date(year, month - 1, day);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    dataDate.setHours(0, 0, 0, 0);

    const diffDays = Math.round((today.getTime() - dataDate.getTime()) / (1000 * 60 * 60 * 24));

    const formatted = dataDate.toLocaleDateString("cs-CZ", {
      day: "numeric",
      month: "numeric",
      year: "numeric",
    });

    // Barevné kódování podle stáří dat
    let color = "var(--text-muted)";
    let prefix = "";
    if (diffDays === 0) {
      color = "var(--bullish)";
      prefix = "";
    } else if (diffDays === 1) {
      color = "#f59e0b"; // amber
      prefix = "⚠️ ";
    } else if (diffDays >= 2) {
      color = "var(--bearish)";
      prefix = "🔴 ";
    }

    return (
      <span style={{
        fontSize: "11px",
        color,
        whiteSpace: "nowrap",
        fontWeight: diffDays >= 1 ? 600 : 400,
      }}>
        {prefix}Aktualizováno k {formatted}
        {diffDays >= 2 && (
          <span style={{ marginLeft: "4px", fontSize: "10px" }}>
            ({diffDays}d stará data)
          </span>
        )}
      </span>
    );
  } catch {
    return null;
  }
}

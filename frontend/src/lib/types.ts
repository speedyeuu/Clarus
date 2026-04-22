// Typy pro celý projekt
export interface DailyScore {
  id: string;
  date: string;
  pair: string;
  score_interest_rates: number | null;
  score_inflation: number | null;
  score_gdp: number | null;
  score_labor: number | null;
  score_cot: number | null;
  score_spmi: number | null;
  score_mpmi: number | null;
  score_retail_sales: number | null;
  score_trend: number | null;
  score_retail_sentiment: number | null;
  score_seasonality: number | null;
  weights: Record<string, number>;
  total_score: number;
  label: string;
}

export interface Prediction {
  id: string;
  created_date: string;
  prediction_date: string;
  predicted_score_low: number;
  predicted_score_high: number;
  predicted_score_mid: number;
  confidence: number;
  actual_score: number | null;
  accuracy_score: number | null;
}

export interface UpcomingEvent {
  id: string;
  event_date: string;
  event_time: string;
  title: string;
  country: 'USD' | 'EUR';
  impact: 'High' | 'Medium' | 'Low';
  indicator_key: string;
  forecast: string | null;
  previous: string | null;
  polymarket_yes_prob: number | null;
  euribor_signal: number | null;
}

export interface AutoresearchLog {
  id: string;
  run_date: string;
  old_weights: Record<string, number>;
  new_weights: Record<string, number>;
  improvement_notes: string;
  reasoning: string;
  confidence: number;
  applied: boolean;
  rejected: boolean;
}

export interface AccuracySummary {
  week_avg: number | null;
  month_avg: number | null;
  week_count: number;
  month_count: number;
}

// =============================================
// INDIKÁTOR METADATA (label, pořadí)
// =============================================
export const INDICATOR_META: Record<string, { label: string; weight_key: string; order: number; tooltip: string }> = {
  score_interest_rates: {
    label: "Interest Rates", weight_key: "interest_rates", order: 1,
    tooltip: "Úrokové sazby ECB (EUR) a FEDu (USD). Vyšší sazby přitahují kapitál a posilují měnu. Pokud ECB zvyšuje agresivněji než FED, EUR/USD roste — a naopak. Klíčové jsou zasedání centrálních bank a jejich výhled (hawkish = býčí, dovish = medvědí).",
  },
  score_inflation: {
    label: "Inflation", weight_key: "inflation", order: 2,
    tooltip: "Inflace (CPI/HICP) určuje, jak moc centrální banka tlačí na sazby. Vysoká inflace v eurozóně → ECB zpřísňuje → EUR posiluje. Vysoká inflace v USA → FED zpřísňuje → EUR/USD klesá. Trh reaguje hlavně na překvapení oproti prognóze.",
  },
  score_gdp: {
    label: "GDP", weight_key: "gdp", order: 3,
    tooltip: "Hrubý domácí produkt měří celkový ekonomický výkon. Silný GDP eurozóny signalizuje zdravou ekonomiku a posiluje EUR vůči USD. Důležité je srovnání obou stran a míra překvapení — trh kupuje, co překvapí pozitivně.",
  },
  score_labor: {
    label: "Labor", weight_key: "labor", order: 4,
    tooltip: "Trh práce (nezaměstnanost, mzdy). Nízká nezaměstnanost a silné mzdy vytvářejí inflační tlak → centrální banka zvyšuje sazby. Silný americký trh práce tlačí USD nahoru a EUR/USD dolů — a naopak.",
  },
  score_cot: {
    label: "COT Bias", weight_key: "cot", order: 5,
    tooltip: "Ukazuje, jak velcí institucionální hráči drží pozice na EUR a americkém dolaru. Silná net-long pozice na EUR = smart money čeká posílení EUR — jde o spolehlivý dlouhodobý sentiment indikátor.",
  },
  score_spmi: {
    label: "Services PMI", weight_key: "spmi", order: 6,
    tooltip: "Index aktivity ve službách (průzkum mezi manažery firem). Hodnoty nad 50 = expanze, pod 50 = kontrakce. Sektor služeb tvoří většinu ekonomiky eurozóny — silné EU PMI vs. slabé USA PMI = bullish EUR/USD.",
  },
  score_mpmi: {
    label: "Manuf. PMI", weight_key: "mpmi", order: 7,
    tooltip: "Index aktivity ve výrobním sektoru. Stejná logika jako Services PMI, ale méně výrazný vliv. Klíčový pro Německo — slabé německé výrobní PMI bývá bearish pro celé EUR.",
  },
  score_retail_sales: {
    label: "Retail Sales", weight_key: "retail_sales", order: 8,
    tooltip: "Maloobchodní tržby měří spotřebitelské výdaje — klíčový ukazatel ekonomické síly. Silné tržby v eurozóně = silnější EUR. Trh reaguje především na překvapení vůči prognóze, samotná absolutní čísla jsou méně podstatná.",
  },
  score_trend: {
    label: "Trend", weight_key: "trend", order: 9,
    tooltip: "Technický makro-trend EUR/USD z denních svíček. Kombinuje EMA 20, EMA 50 a ADX — ukazuje sílu a směr trendu. Pozitivní trend potvrzuje fundamentální bullish signál, negativní varuje před vstupem.",
  },
  score_retail_sentiment: {
    label: "Retail Sentiment", weight_key: "retail_sentiment", order: 10,
    tooltip: "Kontraindikátor! Ukazuje pozice malých retailových obchodníků. Pokud 80 % retailu shortuje EUR/USD, velcí hráči jsou pravděpodobně na opačné straně → bullish signál. Dav se mýlí — sledujeme ho obráceně.",
  },
  score_seasonality: {
    label: "Seasonality", weight_key: "seasonality", order: 11,
    tooltip: "Historické sezónní vzory EUR/USD. Prosinec bývá silný pro EUR (end-of-year rally), březen naopak slabý. Jde o statistický průměr z historických dat — doplňkový kontext, ne zákonité pravidlo.",
  },
};

// =============================================
// SCORE → LABEL + COLOR
// =============================================
export function getScoreLabel(score: number): string {
  if (score >= 2.0)  return "Strong Bullish";
  if (score >= 1.0)  return "Bullish";
  if (score >= 0.33) return "Mildly Bullish";
  if (score > -0.33) return "Neutral";
  if (score > -1.0)  return "Mildly Bearish";
  if (score > -2.0)  return "Bearish";
  return "Strong Bearish";
}

export function getScoreColor(score: number | null): string {
  if (score === null) return "var(--neutral)";
  if (score >= 1.0)  return "var(--bullish)";
  if (score >= 0.33) return "var(--mild-bullish)";
  if (score > -0.33) return "var(--neutral)";
  if (score > -1.0)  return "var(--mild-bearish)";
  return "var(--bearish)";
}

export function getScoreEmoji(label: string): string {
  const map: Record<string, string> = {
    "Strong Bullish": "🟢",
    "Bullish":        "🟡",
    "Mildly Bullish": "🟡",
    "Neutral":        "⚪",
    "Mildly Bearish": "🟠",
    "Bearish":        "🟠",
    "Strong Bearish": "🔴",
  };
  return map[label] ?? "⚪";
}

// Score bar: převod -3..+3 na procentuální pozici pro CSS
// Vrátí { left, width, color } pro absolutně pozicovaný fill
export function scoreToBar(score: number | null): { left: string; width: string; color: string } {
  if (score === null) return { left: "50%", width: "0%", color: "var(--neutral)" };
  const clamped = Math.max(-3, Math.min(3, score));
  const color = getScoreColor(score);
  if (clamped >= 0) {
    return { left: "50%", width: `${(clamped / 3) * 50}%`, color };
  } else {
    const pct = (Math.abs(clamped) / 3) * 50;
    return { left: `${50 - pct}%`, width: `${pct}%`, color };
  }
}

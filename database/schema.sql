-- ============================================================
-- EUR/USD Fundamental Analyzer – Supabase Schema
-- Spustit v Supabase SQL Editor (Settings > SQL Editor)
-- ============================================================

-- Rozšíření
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ============================================================
-- 1. HISTORICKÁ DATA INDIKÁTORŮ
-- ============================================================
CREATE TABLE IF NOT EXISTS indicator_readings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date          DATE NOT NULL,
  indicator_name TEXT NOT NULL,      -- 'cpi_us', 'nfp', 'ecb_rate', 'cot_bias' atd.
  pair          TEXT NOT NULL DEFAULT 'EURUSD',
  actual        FLOAT,
  forecast      FLOAT,
  previous      FLOAT,
  surprise      FLOAT,               -- actual - forecast
  surprise_zscore FLOAT,             -- normalizovaný surprise
  raw_score     FLOAT,               -- -3.0 až +3.0 (float, bez zaokrouhlování)
  direction     TEXT,                -- 'USD_BULLISH' | 'EUR_BULLISH' | 'NEUTRAL'
  source        TEXT,                -- 'forex_factory' | 'cftc' | 'oanda' | 'manual'
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_indicator_readings_date         ON indicator_readings(date DESC);
CREATE INDEX IF NOT EXISTS idx_indicator_readings_name_date    ON indicator_readings(indicator_name, date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_indicator_date            ON indicator_readings(date, indicator_name, pair);


-- ============================================================
-- 2. DENNÍ AGREGOVANÉ SKÓRE
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_scores (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date          DATE NOT NULL UNIQUE,
  pair          TEXT NOT NULL DEFAULT 'EURUSD',

  -- Skóre jednotlivých indikátorů (float -3 až +3, poslední dostupná hodnota)
  score_interest_rates   FLOAT,
  score_inflation        FLOAT,
  score_gdp              FLOAT,
  score_labor            FLOAT,
  score_cot              FLOAT,
  score_spmi             FLOAT,
  score_mpmi             FLOAT,
  score_retail_sales     FLOAT,
  score_trend            FLOAT,
  score_retail_sentiment FLOAT,
  score_seasonality      FLOAT,

  -- Váhy použité tento den
  weights       JSONB,

  -- Výsledné skóre
  total_score   FLOAT,               -- vážený součet, float v [-3, +3]
  label         TEXT,                -- 'Strong Bullish' | 'Bullish' | ... | 'Strong Bearish'

  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_scores_date ON daily_scores(date DESC);


-- ============================================================
-- 3. PREDIKCE (7 dní dopředu)
-- ============================================================
CREATE TABLE IF NOT EXISTS predictions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_date        DATE NOT NULL,       -- kdy byla predikce vytvořena
  prediction_date     DATE NOT NULL,       -- na který den predikuje
  pair                TEXT NOT NULL DEFAULT 'EURUSD',

  predicted_score_low  FLOAT,             -- spodní hranice zóny
  predicted_score_high FLOAT,             -- horní hranice zóny
  predicted_score_mid  FLOAT,             -- střed

  confidence          FLOAT,              -- 0.0 - 1.0
  polymarket_probabilities JSONB,         -- raw data z Polymarketu
  euribor_signal      FLOAT,              -- OIS/EURIBOR implicovaná ECB pravděpodobnost
  upcoming_events     JSONB,              -- jaké události se očekávají

  -- Vyhodnocení přesnosti (doplní se zpětně)
  actual_score        FLOAT,              -- doplní se po skutečném dni
  accuracy_score      FLOAT,             -- jak přesná byla predikce (0.0 - 1.0)

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(created_date, prediction_date, pair)
);

CREATE INDEX IF NOT EXISTS idx_predictions_created   ON predictions(created_date DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_pred_date ON predictions(prediction_date ASC);


-- ============================================================
-- 4. AUTORESEARCH LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS autoresearch_log (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_date         DATE NOT NULL,
  old_weights      JSONB,
  new_weights      JSONB,
  improvement_notes TEXT,             -- co LLM navrhlo
  reasoning        TEXT,              -- detailní zdůvodnění od Claude
  accuracy_before  FLOAT,
  accuracy_after   FLOAT,             -- odhadovaná (doplní se po aplikaci)
  confidence       FLOAT,             -- 0.0 - 1.0
  applied          BOOLEAN DEFAULT FALSE,
  rejected         BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================
-- 5. NORMALIZAČNÍ STATISTIKY (pro z-score výpočet)
-- ============================================================
CREATE TABLE IF NOT EXISTS normalization_stats (
  indicator_name  TEXT PRIMARY KEY,
  lookback_days   INT DEFAULT 365,
  mean_surprise   FLOAT,
  std_surprise    FLOAT,
  sample_count    INT DEFAULT 0,
  -- Hardcoded defaults (platí dokud nemáme 30+ vzorků)
  default_std     FLOAT,             -- konzervativní odhad ze znalosti trhu
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Seed výchozí normalizační hodnoty (konzervativní odhady z histórie trhu)
INSERT INTO normalization_stats (indicator_name, default_std, mean_surprise) VALUES
  ('cpi_us',           0.10, 0.0),   -- CPI USA: typická odchylka ~0.10 p.p.
  ('cpi_eu',           0.10, 0.0),
  ('pce_us',           0.10, 0.0),
  ('nfp_us',           50.0, 0.0),   -- NFP: typická odchylka ~50k jobs
  ('unemployment_us',  0.10, 0.0),
  ('gdp_flash_us',     0.30, 0.0),   -- GDP Flash: typická odchylka ~0.3 p.p.
  ('gdp_flash_eu',     0.20, 0.0),
  ('fed_rate',         0.25, 0.0),   -- Rate decisions: 0/25/50 bps
  ('ecb_rate',         0.25, 0.0),
  ('spmi_us',          1.00, 0.0),   -- PMI: typická odchylka ~1 bod
  ('spmi_eu',          1.00, 0.0),
  ('mpmi_us',          1.00, 0.0),
  ('mpmi_eu',          1.00, 0.0),
  ('retail_sales_us',  0.30, 0.0),
  ('retail_sales_eu',  0.30, 0.0)
ON CONFLICT (indicator_name) DO NOTHING;


-- ============================================================
-- 6. VÁHY (aktuální konfigurace indikátorů)
-- ============================================================
CREATE TABLE IF NOT EXISTS weight_settings (
  id            TEXT PRIMARY KEY DEFAULT 'current',
  weights       JSONB NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Výchozí váhy (z plan.md)
INSERT INTO weight_settings (id, weights) VALUES (
  'current',
  '{
    "interest_rates":    0.22,
    "inflation":         0.20,
    "gdp":               0.13,
    "labor":             0.12,
    "cot":               0.11,
    "spmi":              0.08,
    "mpmi":              0.06,
    "retail_sales":      0.05,
    "trend":             0.05,
    "retail_sentiment":  0.04,
    "seasonality":       0.02
  }'::jsonb
) ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- 7. NADCHÁZEJÍCÍ UDÁLOSTI (cache z Forex Factory)
-- ============================================================
CREATE TABLE IF NOT EXISTS upcoming_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_date    DATE NOT NULL,
  event_time    TEXT,                 -- '13:30' UTC
  title         TEXT NOT NULL,        -- 'US CPI m/m'
  country       TEXT NOT NULL,        -- 'USD' | 'EUR'
  impact        TEXT,                 -- 'High' | 'Medium' | 'Low'
  indicator_key TEXT,                 -- mapování na náš indikátor ('cpi_us')
  forecast      TEXT,                 -- jako string ('0.3%')
  previous      TEXT,
  polymarket_yes_prob FLOAT,          -- pravděpodobnost z Polymarketu (null pokud N/A)
  euribor_signal      FLOAT,          -- pro ECB events
  fetched_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(event_date, title, country)
);

CREATE INDEX IF NOT EXISTS idx_upcoming_events_date ON upcoming_events(event_date ASC);


-- ============================================================
-- RLS (Row Level Security) – pro MVP vypnuto, service role má přístup
-- ============================================================
ALTER TABLE indicator_readings    DISABLE ROW LEVEL SECURITY;
ALTER TABLE daily_scores          DISABLE ROW LEVEL SECURITY;
ALTER TABLE predictions           DISABLE ROW LEVEL SECURITY;
ALTER TABLE autoresearch_log      DISABLE ROW LEVEL SECURITY;
ALTER TABLE normalization_stats   DISABLE ROW LEVEL SECURITY;
ALTER TABLE weight_settings       DISABLE ROW LEVEL SECURITY;
ALTER TABLE upcoming_events       DISABLE ROW LEVEL SECURITY;

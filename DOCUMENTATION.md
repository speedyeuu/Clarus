# EUR/USD Fundamental Analyzer – Kompletní technická dokumentace

> **Verze:** 1.0 | **Datum:** Duben 2026 | **Autor:** Filip Černý  
> Systém pro automatickou fundamentální analýzu měnového páru EUR/USD s predikčním enginem a AI autoresearch modulem.

---

## Obsah
1. [Přehled architektury](#1-přehled-architektury)
2. [Databázové schéma (Supabase)](#2-databázové-schéma-supabase)
3. [Backend – Datové sběrače (Collectors)](#3-backend--datové-sběrače-collectors)
4. [Backend – Scoring Engine](#4-backend--scoring-engine)
5. [Backend – Pipeline (Daily Update)](#5-backend--pipeline-daily-update)
6. [Backend – Predikční modul](#6-backend--predikční-modul)
7. [Backend – Autoresearch (AI Optimalizace)](#7-backend--autoresearch-ai-optimalizace)
8. [Backend – API Endpointy](#8-backend--api-endpointy)
9. [Frontend (Next.js)](#9-frontend-nextjs)
10. [Seedování databáze](#10-seedování-databáze)
11. [Časování a Cron](#11-časování-a-cron)
12. [Klíče a konfigurace (.env)](#12-klíče-a-konfigurace-env)
13. [Tok dat – celý cyklus end-to-end](#13-tok-dat--celý-cyklus-end-to-end)
14. [Vzorce a matematika](#14-vzorce-a-matematika)
15. [Multi-pair rozšíření (budoucnost)](#15-multi-pair-rozšíření-budoucnost)

---

## 1. Přehled architektury

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 16)                    │
│         Dashboard • Graf skóre • Predikce • Admin           │
│                   http://localhost:3000                     │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST API (JSON)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI / Python)                │
│                   http://localhost:8000                     │
│                                                             │
│  /api/score     /api/predictions  /api/events               │
│  /api/autoresearch               /api/cron/update           │
└──────────┬────────────────────────────────────┬─────────────┘
           │ Čtení dat                          │ Zápis výsledků
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────┐
│                  SUPABASE (PostgreSQL)                      │
│  indicator_readings • daily_scores • predictions            │
│  normalization_stats • weight_settings • upcoming_events    │
│  autoresearch_log                                           │
└─────────────────────────────────────────────────────────────┘
           ▲
           │ Sběr dat (každý večer 19:00 UTC)
           │
┌──────────┴─────────────────────────────────────────────────┐
│                  COLLECTORS (Python)                        │
│                                                             │
│  ForexFactory   CFTC.gov   Alpha Vantage   EODHD           │
│  MyFXBook       Polymarket  EURIBOR                        │
└────────────────────────────────────────────────────────────┘
```

### Technologický stack

| Vrstva | Technologie | Verze |
|--------|-------------|-------|
| Backend API | FastAPI + Uvicorn | Python 3.13 |
| Frontend | Next.js (App Router) | 16+ |
| Databáze | Supabase (PostgreSQL) | cloud |
| HTTP klient | httpx | async |
| Datová analýza | pandas, pandas-ta, numpy | latest |
| AI (Autoresearch) | Google Gemini 2.5 Flash | API |
| Sentiment | MyFXBook Community API | zdarma |
| COT data | CFTC.gov Socrata API | zdarma |
| Kalibrace | FRED (Federal Reserve) | zdarma |
| Forex OHLC | Alpha Vantage + EODHD | freemium |

---

## 2. Databázové schéma (Supabase)

### Tabulka `indicator_readings`
Ukládá **surové denní hodnoty každého indikátoru**.

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | uuid | PK |
| `pair` | text | Měnový pár (default: `EURUSD`) |
| `date` | date | Den výpočtu |
| `indicator_key` | text | Kód indikátoru např. `inflation` |
| `raw_value` | float | Surové sub-skóre před vážením (-3 až +3) |
| `data_source` | text | Odkud data pochází (`forex_factory`, `cftc`, …) |

### Tabulka `daily_scores`
Ukládá **výsledné celkové skóre** pro každý den a pár.

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | uuid | PK |
| `pair` | text | `EURUSD` |
| `date` | date | Den výpočtu |
| `total_score` | float | Vážený součet (-3.0 až +3.0) |
| `label` | text | `Strong Bullish`, `Bullish`, `Mildly Bullish`, `Neutral`, `Mildly Bearish`, `Bearish`, `Strong Bearish` |
| `scores_breakdown` | jsonb | Slovník `{indicator: sub_score}` |
| `weights_used` | jsonb | Slovník `{indicator: weight}` použitých vah |

### Tabulka `predictions`
7denní prognóza vygenerovaná každý večer.

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | uuid | PK |
| `pair` | text | `EURUSD` |
| `created_date` | date | Den kdy predikce vznikla |
| `prediction_date` | date | Den na který predikce platí |
| `predicted_score_mid` | float | Střední odhad skóre |
| `predicted_score_low` | float | Dolní hranice pásma nejistoty |
| `predicted_score_high` | float | Horní hranice pásma nejistoty |
| `confidence` | float | Jistota modelu 0.0–1.0 |
| `accuracy_score` | float | Zpětně vyhodnocená přesnost (doplní se po datu) |
| `upcoming_events` | jsonb | Seznam názvů událostí které ovlivnily predikci |

### Tabulka `normalization_stats`
Parametry Z-Score kalibrátoru, naplněné seedem.

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `indicator_name` | text | PK, např. `inflation` |
| `mean_surprise` | float | Průměrný historický „surprise" (%) |
| `std_surprise` | float | Směrodatná odchylka surprise (%) |

### Tabulka `weight_settings`
Aktuálně platné váhy indikátorů (spravovatelné přes Admin UI).

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | text | PK, vždy hodnota `current` |
| `weights` | jsonb | `{"interest_rates": 0.22, "inflation": 0.20, …}` |
| `updated_at` | timestamp | Kdy byly naposledy změněny |

### Tabulka `upcoming_events`
Budoucí makro události s doplněnými Polymarket pravděpodobnostmi.

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | uuid | PK |
| `event_date` | date | Datum události |
| `pair` | text | Měnový pár |
| `title` | text | Název události z ForexFactory |
| `country` | text | `USD` nebo `EUR` |
| `impact` | text | `High` / `Medium` |
| `indicator_key` | text | Mapovaný indikátor |
| `forecast` | text | Konsensus odhad (ze FF) |
| `previous` | text | Předchozí hodnota |
| `polymarket_yes_prob` | float | Pravděpodobnost „YES" z Polymarketu (0–1) |
| `euribor_signal` | float | OIS signal z EURIBOR futures |

### Tabulka `autoresearch_log`
Historie návrhů vah od Gemini AI.

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `id` | uuid | PK |
| `run_date` | date | Kdy byl návrh vygenerován |
| `old_weights` | jsonb | Staré váhy před návrhem |
| `new_weights` | jsonb | Navrhované nové váhy |
| `reasoning` | text | Zdůvodnění od AI (anglicky) |
| `improvement_notes` | text | Krátké shrnutí změn |
| `accuracy_before` | float | Průměrná přesnost predikcí před návrhem |
| `confidence` | float | Sebejistota AI (0–1) |
| `applied` | bool | Zda byly váhy schváleny adminem |
| `rejected` | bool | Zda byly zamítnuty |

---

## 3. Backend – Datové sběrače (Collectors)

### 3.1 `collectors/forex_factory.py` – Makro kalendář
**Zdroj:** `https://nfs.faireconomy.media/ff_calendar_thisweek.json`  
**Cena:** Zdarma, bez API klíče  
**Frekvence stahování:** Každý den v 19:00 UTC (daily pipeline)

**Co stahuje:**
- JSON seznam všech makroekonomických událostí pro aktuální týden
- Filtruje pouze `country ∈ {USD, EUR}` a `impact ∈ {High, Medium}`

**Výstupní model `FFEvent`:**
```python
title: str      # "Non-Farm Employment Change"
country: str    # "USD"
date: datetime  # 2026-04-08T12:30:00
impact: str     # "High"
forecast: str   # "175K"
previous: str   # "151K"
actual: str     # "228K" (prázdné do vyhlášení)
indicator_key: str  # "labor" (mapováno přes TITLE_TO_INDICATOR)
```

**Mapovací tabulka `TITLE_TO_INDICATOR`:**

| Název z FF | Náš klíč |
|-----------|----------|
| CPI m/m, Core CPI m/m | `inflation` |
| Non-Farm Employment Change, Unemployment Rate | `labor` |
| Advance GDP q/q, Flash GDP q/q | `gdp` |
| Flash Manufacturing PMI, ISM Manufacturing PMI | `mpmi` |
| Flash Services PMI, ISM Services PMI | `spmi` |
| Retail Sales m/m, Core Retail Sales m/m | `retail_sales` |
| Federal Funds Rate, Main Refinancing Rate | `interest_rates` |
| FOMC Statement, Monetary Policy Statement | `interest_rates` |

---

### 3.2 `collectors/cot.py` – COT Report (Commitment of Traders)
**Zdroj:** `https://publicreporting.cftc.gov/resource/6dca-aqww.json` (CFTC Socrata API)  
**Cena:** Zdarma, bez registrace, bez API klíče  
**Frekvence:** Páteční COT report vychází každý pátek po 15:30 ET

**Co stahuje:**
- Pozice Non-Commercial (velcí spekulanti) pro EUR FX a USD Index
- 52 týdnů historických dat pro kalibraci percentilů

**Výstup `COTData`:**
```python
eur_net_position: int       # Long - Short pozice EUR spekulantů
dxy_net_position: int       # Long - Short pozice USD Index spekulantů
eur_history_52w: List[int]  # 52 týdenních net pozic EUR
dxy_history_52w: List[int]  # 52 týdenních net pozic DXY
```

**Použité tickery:**
- `EURO FX - CHICAGO MERCANTILE EXCHANGE`
- `USD INDEX - ICE FUTURES U.S.` *(přejmenováno v únoru 2022)*

---

### 3.3 `collectors/sentiment.py` – Retail Sentiment
**Zdroj:** MyFXBook Community Outlook API  
**Cena:** Zdarma, potřeba účet (email + heslo)  
**Frekvence:** Denně v pipeline

**Tok:**
1. POST přihlášení → `https://www.myfxbook.com/api/login.json?email=…&password=…` → `session_id`
2. GET data → `https://www.myfxbook.com/api/get-community-outlook.json?session={session_id}`
3. Vyfiltruje symbol `EURUSD`

**Výstup `SentimentData`:**
```python
long_pct: float   # 0.27 = 27% traderů kupuje EUR
short_pct: float  # 0.73 = 73% traderů prodává EUR
```

> **Logika kontraindikátoru:** Velká část amatérů kupuje = trh bude padat (a naopak).

---

### 3.4 `collectors/price.py` – Cena EUR/USD (OHLC data)
**Zdroj:** Alpha Vantage (primární) | EODHD (historické)  
**Cena:** Alpha Vantage – zdarma 25 req/den

**Alpha Vantage endpoint:**
```
https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey={KEY}
```

**Výstup:** `pandas.DataFrame` se sloupci `open, high, low, close` indexovaný podle data

Využívá se pro:
- Výpočet EMA 20, EMA 50, ADX (technický trend)
- Kalibraci roční historie v seedu (EODHD – 8032 svíček od r.2002)

---

### 3.5 `collectors/polymarket.py` – Tržní pravděpodobnosti
**Zdroj:** Polymarket Gamma API – `https://gamma-api.polymarket.com/markets`  
**Cena:** Zdarma, bez API klíče  
**Frekvence:** Denně v pipeline

**Co stahuje:**
- Seznam aktivních trhů z kategorie Economics/Finance
- Pro každý trh vrátí `yes_probability` (0–1)

**Výstup `PolymarketMarket`:**
```python
id: str
title: str          # "Will US CPI be below 0.3% in April?"
yes_probability: float  # 0.44
```

**Fuzzy párování (`extract_signal_from_polymarket`):**

Funkce porovnává název FF události s tituly trhů na Polymarketu:

| FF název obsahuje | Hledaná klíčová slova na Polymarketu |
|------------------|--------------------------------------|
| `cpi`, `inflation` | `cpi`, `inflation` |
| `non-farm`, `nfp`, `employment` | `nfp`, `nonfarm`, `payrolls` |
| `gdp` | `gdp` |
| `rate` + (`fed`/`fomc`) | `fed`, `rate`, `cut` |
| `jobless claims` | `jobless claims` |

Nalezená pravděpodobnost se uloží do `upcoming_events.polymarket_yes_prob`.

---

### 3.6 `collectors/euribor.py` – ECB úrokové expectace
**Zdroj:** EODHD (Futures data – EURIBOR kontrakty)  
**Cena:** EODHD plán $19.99/měsíc  

Stahuje nejbližší EURIBOR futures kontrakt. Z ceny vypočítá **implicitní sazbu** (100 - cena = sazba v %).  
Výsledek se ukládá do `upcoming_events.euribor_signal` jako pravděpodobnost rate cutu.

---

## 4. Backend – Scoring Engine

### 4.1 Normalizér (`scoring/normalizer.py`)
Převádí surové ekonomické číslo na naši škálu **-3 až +3**.

**Z-Score vzorec:**
```
surprise  = actual - forecast
z_score   = (surprise - mean_surprise) / std_surprise
score     = clamp(z_score, -3.0, +3.0)
```

Kde `mean_surprise` a `std_surprise` pochází z tabulky `normalization_stats` (naplněné seedem z FRED API).

**Příklad:**
- CPI actual: `0.4%`, forecast: `0.2%`
- surprise: `+0.20`
- mean: `0.29`, std: `0.34`
- z_score: `(0.20 - 0.29) / 0.34 = -0.26`
- score: `-0.26` → mírně negativní (USD mírně posílil)

---

### 4.2 Indikátory (`scoring/indicators.py`)

#### `score_ff_event()` – Makroekonomická zpráva
Wrapper kolem Z-Score normalizátoru. Parametr `invert=True` převrátí výsledek (pro USD zprávy – silná ekonomika USA → EUR klesá → záporné skóre pro náš bullish EUR index).

#### `score_sentiment()` – Retail kontraindikátor
```
delta = long_pct - short_pct
score = delta / -20.0
```
- `long_pct = 0.80` → delta = `+60` → score = `-3.0` (extrémně bearish)
- `long_pct = 0.20` → delta = `-60` → score = `+3.0` (extrémně bullish)

#### `score_trend()` – Technický trend
Počítá pomocí `pandas-ta`:
1. EMA 20 a EMA 50 (exponenciální klouzavé průměry)
2. ADX 14 (síla trendu)

**Logika:**
```
dir_score = 0
if close > EMA20: dir_score += 1  else: dir_score -= 1
if EMA20 > EMA50: dir_score += 1  else: dir_score -= 1

multiplier = 0.5         # ADX < 25 (slabý trend)
multiplier = 1.0         # ADX 25-40 (střední trend)
multiplier = 1.5         # ADX > 40 (silný trend)

final = clamp(dir_score * multiplier, -3.0, +3.0)
```

#### `score_seasonality()` – Historická sezónnost
Hardcoded tabulka měsíčních průměrů z 20 let dat:

| Měsíc | Skóre | Vysvětlení |
|-------|-------|------------|
| Leden | -1.0 | Silnější USD, repatriace |
| Březen | -1.5 | USD repatriace konec Q1 |
| Duben | +1.0 | Tradičně dobrý pro EUR |
| Prosinec | +2.5 | End-of-Year EUR rally |

---

### 4.3 Engine (`scoring/engine.py`) – Vážený součet

**Výchozí váhy:**

| Indikátor | Váha | Odůvodnění |
|-----------|------|-----------|
| `interest_rates` | 22% | ECB/FED rozhodnutí nejvíce hýbají trhem |
| `inflation` | 20% | Klíčový input do rozhodnutí centrálních bank |
| `gdp` | 13% | Ekonomický růst |
| `labor` | 12% | NFP je největší USD report |
| `cot` | 11% | Velký spekulanti vedou trend |
| `spmi` | 8% | Services PMI předbíhá ekonomický cyklus |
| `mpmi` | 6% | Manufacturing PMI |
| `retail_sales` | 5% | Spotřebitelská poptávka |
| `trend` | 5% | Technická složka |
| `retail_sentiment` | 4% | MyFXBook kontraindikátor |
| `seasonality` | 2% | Historická sezónnost |
| **Suma** | **100%** | |

**Vzorec výsledného skóre:**
```
total_score = Σ (sub_score[i] × weight[i])
total_score = clamp(total_score, -3.0, +3.0)
```

**Labelování:**

| Hodnota | Label |
|---------|-------|
| ≥ 2.0 | Strong Bullish |
| ≥ 1.0 | Bullish |
| ≥ 0.33 | Mildly Bullish |
| > -0.33 | Neutral |
| > -1.0 | Mildly Bearish |
| > -2.0 | Bearish |
| ≤ -2.0 | Strong Bearish |

---

## 5. Backend – Pipeline (Daily Update)

**Soubor:** `backend/scheduler/daily_update.py`  
**Spuštění:** Každý den v **19:00 UTC** (volat přes Cron nebo `POST /api/cron/update`)

### Pořadí kroků:

```
KROK 1: Stažení ForexFactory kalendáře
   └─ fetch_forex_factory_week() → list[FFEvent]
   └─ filter_today_events() → dnešní události

KROK 2: Stažení tržních dat
   ├─ fetch_cot_data()           → COT pozice (CFTC.gov)
   ├─ fetch_retail_sentiment()   → MyFXBook long/short %
   └─ fetch_historical_ohlc()   → DataFrame OHLC (Alpha Vantage)

KROK 3: Výpočet sub-skóre
   ├─ Pro každou dnešní FF událost:
   │   ├─ get_normalization_stats(indicator_key)  ← z Supabase normalization_stats
   │   └─ score_ff_event(actual, forecast, stats, invert)
   ├─ score_sentiment(long_pct, short_pct)
   ├─ score_trend(ohlc_df)
   └─ score_seasonality()

KROK 4: Příprava budoucích událostí
   ├─ fetch_polymarket_economics()  → PolymarketMarket[]
   └─ Pro každou budoucí FF událost:
       └─ extract_signal_from_polymarket(title, markets) → float|None

KROK 5: Výpočet celkového skóre
   └─ calculate_total_score(scores) → DailyScoreModel {total, label, weights}

KROK 6: Uložení do Supabase
   ├─ A) indicator_readings ← surové sub-skóre každého indikátoru
   ├─ B) daily_scores       ← celkové skóre dne
   ├─ C) upcoming_events    ← budoucí události s Polymarket pravd.
   └─ D) predictions        ← generate_7day_prediction() + accuracy check
```

---

## 6. Backend – Predikční modul

**Soubor:** `backend/prediction/generator.py`

### Jak funguje predikce 7 dní dopředu?

Systém generuje každý večer 7 denních predikcí pomocí **auto-regresního modelu s Polymarket signály**.

#### Krok 1 – Mean Reversion Drift
Každý den bez zpráv se skóre přirozeně vrací o **0.05 bodu** směrem k nule:
```python
mean_reversion_daily = 0.05

if score > 0: score -= 0.05
if score < 0: score += 0.05
```
*(Intuice: bez nových informací trh „zapomíná" na extrémní sentiment)*

#### Krok 2 – Polymarket Score Shift
Pro každou budoucí událost s `polymarket_yes_prob`:

```
max_impact = indicator_weight × 3.0

Expected_Value = (prob × max_impact) - ((1 - prob) × max_impact)
               = max_impact × (2×prob - 1)
```

**Příklady:**
- FED Rate Cut s `prob=0.80`, váha `interest_rates=0.22`:
  - `max_impact = 0.22 × 3.0 = 0.66`
  - `shift = 0.66 × (2×0.8 - 1) = 0.66 × 0.6 = +0.396`
  
- 50/50 pravděpodobnost → `shift = 0`
- USD zpráva → `invert=True` → shift se otočí (silná USD ekonomika = -EUR)

#### Krok 3 – Pásmo nejistoty (Confidence Bands)

```
confidence(0 events) = 0.30   → band_width = 0.5 × (1.1 - 0.30) = 0.40
confidence(1 event)  = 0.60   → band_width = 0.5 × (1.1 - 0.60) = 0.25
confidence(2 events) = 0.75   → band_width = 0.5 × (1.1 - 0.75) = 0.175
confidence(3+ events)= 0.85   → band_width = 0.5 × (1.1 - 0.85) = 0.125
```

**Výstup pro každý den:**
```json
{
  "prediction_date": "2026-04-15",
  "predicted_score_mid": 1.24,
  "predicted_score_low":  0.84,
  "predicted_score_high": 1.64,
  "confidence": 0.75,
  "upcoming_events": ["NFP", "Unemployment Rate"]
}
```

### `prediction/accuracy.py` – Zpětné vyhodnocení
Po uplynutí data predikce systém porovná `predicted_score_mid` s reálným `daily_scores.total_score` a uloží `accuracy_score` (0–1, kde 1 = perfektní).

Tento accuracy score se pak používá v **Autoresearch modulu** jako vstup pro AI optimalizaci vah.

---

## 7. Backend – Autoresearch (AI Optimalizace)

**Soubor:** `backend/autoresearch/weight_optimizer.py`

### Kdy se spouští?
V rámci daily pipeline – **automaticky po skórování** – ale pouze pokud je průměrná přesnost predikcí pod 85%.

### Postup:
1. Načte poslední 30 accuracy scores z `predictions`
2. Vypočítá průměrnou přesnost `avg_acc`
3. Pokud `avg_acc < 0.85` → zavolá Google Gemini API
4. Sestaví prompt s aktuálními vahami a stavem trhu
5. Gemini vrátí JSON s novými vahami + zdůvodnění
6. Validace: součet vah musí být v rozsahu `0.95–1.05`
7. Uloží jako **pending návrh** do `autoresearch_log`
8. Admin v UI schválí nebo zamítne → aplikuje do `weight_settings`

### Prompt struktura (zkráceno):
```
You are an expert forex macro quant analyst.
Our recent 7-day prediction accuracy: {avg_acc}%
Current weights: {current_weights}

Adjust weights for current macro environment.
Return strictly JSON: { reasoning, improvement_notes, new_weights, confidence }
```

**Model:** `gemini-2.5-flash` (JSON mode – `response_mime_type: application/json`)

---

## 8. Backend – API Endpointy

Základní URL: `http://localhost:8000`

| Method | Endpoint | Popis |
|--------|----------|-------|
| GET | `/health` | Health check – vrátí `{"status": "ok"}` |
| GET | `/api/score/latest?pair=EURUSD` | Poslední denní skóre |
| GET | `/api/score/history?pair=EURUSD&days=30` | Historie skóre N dní |
| GET | `/api/predictions/?pair=EURUSD` | 7denní predikce |
| GET | `/api/events/upcoming?days=7` | Budoucí události s Polymarket pravd. |
| GET | `/api/autoresearch/log` | Historie AI návrhů |
| GET | `/api/autoresearch/pending` | Neschválené AI návrhy |
| POST | `/api/autoresearch/approve` | Schválit/zamítnout návrh |
| POST | `/api/cron/update` | **Zabezpečený** trigger pro cloud cron |

### Zabezpečení `/api/cron/update`
Vyžaduje HTTP hlavičku:
```
Authorization: Bearer {CRON_SECRET}
```
Kde `CRON_SECRET` je nastaven v `.env`. Bez platného tokenu vrátí **401 Unauthorized**.

---

## 9. Frontend (Next.js)

**Cesta:** `frontend/src/`  
**Framework:** Next.js 16 s App Router  
**Styling:** Tailwind CSS

### Stránky

| Route | Soubor | Obsah |
|-------|--------|-------|
| `/` | `app/page.tsx` | Hlavní dashboard s grafem skóre a predikcí |
| `/admin` | **(Připraveno k implementaci)** | Schvalování AI návrhů vah |

### API klient (`lib/api.ts`)
Centralizovaný async klient který volá backend:
```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL  // http://localhost:8000

fetchLatestScore()   → GET /api/score/latest
fetchScoreHistory()  → GET /api/score/history
fetchPredictions()   → GET /api/predictions/
fetchUpcomingEvents()→ GET /api/events/upcoming
```

---

## 10. Seedování databáze

**Soubor:** `backend/seed.py`  
**Spuštění:** Jednorázově po nasazení

### Co dělá seed?

#### Část 1 – EODHD Forex Data
Stahuje **363 denních EUR/USD svíček** za poslední rok pro kalibrační referenci.
```
GET https://eodhd.com/api/eod/EURUSD.FOREX?from={year_ago}&to={today}&period=d
```

#### Část 2 – FRED Z-Score Kalibrace
Pro každý makroindikátor stáhne historická data z FRED (Federal Reserve, zdarma) a vypočítá statistiky:

| FRED Series | Indikátor | Datových bodů |
|-------------|-----------|---------------|
| `CPIAUCSL` | inflation | 949 |
| `CPILFESL` | core_inflation | 829 |
| `GDP` | gdp | 315 |
| `PAYEMS` | labor | 1046 |
| `UNRATE` | unemployment | 937 |
| `RSXFS` | retail_sales | 409 |
| `CP0000EZ19M086NEST` | eu_inflation | 359 |

```python
changes = series.pct_change().dropna() * 100
mean = np.mean(changes)
std  = np.std(changes)
# → uloží do normalization_stats
```

#### Část 3 – COT Validace
Ověří živé spojení s CFTC.gov a stáhne 52 týdnů COT reportu.

---

## 11. Časování a Cron

### Lokální běh
FastAPI server (`uvicorn`) běží nepřetržitě. **Scheduler je odpojen** – update se spouští externě.

### Cloudový Cron
Na hostingovém provideru (Render, Vercel, Railway) nastavíte Cron Job:

**Čas:** `0 19 * * *` (každý den 19:00 UTC)

**HTTP volání:**
```
POST https://vase-domena.cz/api/cron/update
Headers:
  Authorization: Bearer {CRON_SECRET}
```

### Doporučené cloudové cron služby (zdarma)
- [cron-job.org](https://cron-job.org) – zdarma, neomezeno volání
- Vercel Cron Jobs – zabudováno v Vercel projektu
- Railway Cron – $5/měsíc plán

### Manuální spuštění (lokálně)
```bash
cd backend
python scheduler/daily_update.py
```

---

## 12. Klíče a konfigurace (.env)

**Soubor:** `.env` v kořeni projektu

```env
# Supabase (povinné)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGci...   # Service Role JWT – NUTNO pro zápis!

# Cena EUR/USD
ALPHA_VANTAGE_KEY=xxx              # Zdarma – alphavantage.co

# Historická Forex data + Euribor
EODHD_API_KEY=xxx                  # $19.99/měs – eodhd.com

# Gemini AI (Autoresearch)
GEMINI_API_KEY=AIzaSy...           # Zdarma – aistudio.google.com

# Retail Sentiment (kontraindikátor)
MYFXBOOK_EMAIL=vas@email.cz        # Zdarma – myfxbook.com
MYFXBOOK_PASSWORD=heslo

# Frontend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000

# Bezpečnostní token pro Cloud Cron
CRON_SECRET=TajneHeslo2026!        # Vlastní silné heslo
```

> ⚠️ **POZOR:** `SUPABASE_SERVICE_KEY` musí být JWT token začínající `eyJ...`  
> **Nikdy** nepoužívejte `sb_secret_` nebo `sb_publishable_` tokeny – ty jsou CLI tokeny a nebudou fungovat pro přímý databázový přístup!

### Zdroje klíčů – kde co získat

| Klíč | Cena | URL |
|------|------|-----|
| `SUPABASE_SERVICE_KEY` | Zdarma | supabase.com → Project Settings → API |
| `ALPHA_VANTAGE_KEY` | Zdarma | alphavantage.co/support |
| `EODHD_API_KEY` | $19.99/měs | eodhd.com → Dashboard |
| `GEMINI_API_KEY` | Zdarma (do limitu) | aistudio.google.com/apikey |
| `MYFXBOOK_*` | Zdarma | myfxbook.com (registrace účtu) |
| `CFTC` | Bez klíče | cftc.gov – public API |
| `ForexFactory` | Bez klíče | veřejný JSON endpoint |
| `Polymarket` | Bez klíče | Gamma API – public |

---

## 13. Tok dat – celý cyklus end-to-end

```
19:00 UTC – CRON spustí POST /api/cron/update
   │
   ▼
daily_update.py spustí run_daily_update()
   │
   ├─► ForexFactory → dnešní události (kdo vyhlašoval?)
   │       └─ "CPI m/m: actual=0.4%, forecast=0.2%" → surprise!
   │
   ├─► CFTC.gov → COT pozice
   │       └─ EUR net = -7541 (spekulanti shortují EUR)
   │
   ├─► MyFXBook → retail sentiment
   │       └─ 27% long, 73% short EUR
   │
   ├─► Alpha Vantage → OHLC EUR/USD
   │       └─ Close=1.1719, EMA20=1.1650, EMA50=1.1500
   │
   ├─► Výpočet sub-skóre:
   │       inflation     = Z-Score(0.4, 0.2) = -0.26   (USD posílil)
   │       labor         = Z-Score(228K, 175K) = +2.1  (silné NFP)
   │       cot           = percentil(-7541) = -0.8
   │       sentiment     = (27-73) / -20 = +2.3        (kontra signál bullish)
   │       trend         = (close>EMA20 & EMA20>EMA50) × ADX_mult = +1.5
   │       seasonality   = +1.0 (duben)
   │       interest_rates= 0.0 (dnes žádné oznámení)
   │
   ├─► Engine: total = Σ(score × weight) = 0.87 → "Bullish"
   │
   ├─► Polymarket → budoucí události FF týdne + pravděpodobnosti
   │       "Will US CPI hit 0.3%?" → yes_prob=0.44
   │
   ├─► Predikce 7 dní → daily drift + Polymarket shifty → uložit
   │
   ├─► Autoresearch (pokud accuracy < 85%) → Gemini AI → pending návrh
   │
   └─► Supabase:
           indicator_readings ← {inflation: -0.26, labor: +2.1, ...}
           daily_scores       ← {total: 0.87, label: "Bullish"}
           upcoming_events    ← {CPI příští pátek: polymarket 44%}
           predictions        ← {D+1: 0.82, D+2: 0.77, ... D+7: 0.52}
   │
   ▼
20:00 UTC – Uživatel otevře prohlížeč
   │
   ▼
Next.js dashboard → GET /api/score/latest   → {total: 0.87, label: "Bullish"}
                  → GET /api/score/history  → [30 dnů historických skóre]
                  → GET /api/predictions/  → [7 dní dopředu s pásmy]
                  → GET /api/events/upcoming → [ff události + polymarket %]
```

---

## 14. Vzorce a matematika

### Z-Score normalizace
```
surprise = actual - forecast
z        = (surprise - μ) / σ
score    = clamp(z, -3.0, 3.0)
```

### Weighted Sum (celkové skóre)
```
S = Σᵢ (score_i × weight_i)
S_final = clamp(S, -3.0, 3.0)
```

### COT Sentiment Score
```
# Extrémní pozice: percentil 80+ = silný signál
net = long - short
percentile = scipy.stats.percentileofscore(history_52w, net)

if percentile >= 80:  score = +2.5  # Extrémně long EUR spekulanti
elif percentile >= 65: score = +1.5
elif percentile <= 20: score = -2.5  # Extrémně short → bearish EUR
elif percentile <= 35: score = -1.5
else:                  score = 0.0
```

### Retail Sentiment (kontraindikátor)
```
delta = long_pct - short_pct   [v %]
score = delta / -20.0
# delta +60 (80% long) → score = -3.0 (bearish)
# delta -60 (20% long) → score = +3.0 (bullish)
```

### Technical Trend (EMA + ADX)
```
dir = 0
if close > EMA20: dir += 1 else dir -= 1
if EMA20 > EMA50: dir += 1 else dir -= 1

mult = 0.5 if ADX < 25
     = 1.0 if ADX in [25, 40)
     = 1.5 if ADX >= 40

score = clamp(dir × mult, -3.0, 3.0)
```

### Polymarket Predikční Shift
```
max_impact = weight × 3.0
shift = max_impact × (2 × probability - 1)
      = max_impact × (probability - (1 - probability))
# prob=1.0 → shift = +max_impact
# prob=0.5 → shift = 0
# prob=0.0 → shift = -max_impact
```

### Pásmo nejistoty predikce
```
confidence = f(počet_zpráv_daný_den)   [ 0.30 – 0.85 ]
band_width = 0.5 × (1.1 - confidence)

score_high = clamp(mid + band_width, -3.0, 3.0)
score_low  = clamp(mid - band_width, -3.0, 3.0)
```

---

## 15. Multi-pair rozšíření (budoucnost)

Systém je od základu navrhnutý pro podporu více měnových párů.

### Co je již připraveno:
- Všechny API endpointy přijímají parametr `?pair=EURUSD`
- Tabulky `indicator_readings`, `daily_scores`, `predictions`, `upcoming_events` mají sloupec `pair`
- `fetch_historical_ohlc(days)` stahuje EUR/USD – parametrizovatelné

### Co by bylo potřeba přidat pro nový pár (např. GBP/USD):
1. `collectors/forex_factory.py` → přidat `GBP` do filtru zemí
2. `collectors/cot.py` → přidat ticker `"BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"`
3. `scoring/indicators.py` → přidat `score_seasonality()` pro GBP
4. `scoring/engine.py` → přidat `default_weights` pro `GBPUSD`
5. Seed → spustit FRED kalibraci pro GBP indikátory
6. Frontend → přidat dropdown pro výběr páru

---

## Testování

```bash
# Test všech API napojení
python backend/test_all_apis.py

# Test EODHD endpointů
python backend/test_eodhd.py

# Test CFTC přímého API
python backend/test_cftc.py

# Naplnění testovacích dat (mock)
python backend/seed_mock_data.py

# Ostrý seed (potřeba API klíče)
python backend/seed.py
```

---

*Dokumentace vytvořena April 2026. Projekt je ve stavu Production-Ready MVP.*

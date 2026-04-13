# EUR/USD Swing Trader – Fundamental Analyzer & Predictor
## Kompletní projektový plán pro Antigravity

---

## ⚠️ KRITICKÁ ANALÝZA PŘED IMPLEMENTACÍ

Před plánem je důležité vyřešit několik zásadních konceptuálních otázek, které by jinak vedly k chybné implementaci.

### 1. Problém s váhami na Forex Factory (odpověď na tvoji otázku)

Máš pravdu, že si toho všiml – je to důležité. Na Forex Factory má každá událost **pevně přiřazenou ikonu dopadu** (červená/oranžová/žlutá = High/Medium/Low). **Tato ikona se nemění** – CPI je vždy High, Retail Sales je vždy Medium atd.

**ALE** – tvůj problém není s ikonou dopadu, ale s **hodnotou čísla** (actual). Například:
- Jednou vyjde CPI = 3.5 % → actual = 3.5
- Podruhé vyjde CPI = 0.2 % → actual = 0.2

Toto číslo nelze přímo porovnávat. Řešení: **normalizace přes surprise faktor**:

```
Surprise Score = (Actual - Forecast) / Historická_StdDev(Surprise)
```

Tím dostaneš vždy číslo ve stejném měřítku (typicky -3 až +3 sigma), které pak zmapuješ přímo na škálu **-3 až +3** (celá čísla).

---

### 2. Škála -3 až +3 – jen celá čísla

**Škála každého indikátoru:** celá čísla **-3, -2, -1, 0, +1, +2, +3** (žádná desetinná místa).

**Výsledné celkové skóre:** vážený součet individuálních skóre, zaokrouhlený na nejbližší celé číslo. Rozsah výsledku je vždy v [-3, +3].

Výhody:
- Jednoznačná, lidsky čitelná hodnota
- Snadné zobrazení v UI (žádné 1.73...)
- Stále dostatečná nuance pro 11 indikátorů

**Mapování na bullish/bearish:**
| Skóre | Label |
|-------|-------|
| +3 | 🟢 Strong Bullish |
| +2 | 🟡 Bullish |
| +1 | 🟡 Mildly Bullish |
| 0 | ⚪ Neutral |
| -1 | 🟠 Mildly Bearish |
| -2 | 🟠 Bearish |
| -3 | 🔴 Strong Bearish |

---

### 3. Váhy – doporučení pro max 2týdenní swing trading EUR/USD

Logika vychází z:
- **Frekvence vydání** – co vychází týdně/denně, má aktuálnější vliv
- **Tržní reakce** – co historicky hýbe EUR/USD nejvíce
- **Persistentnost** – jak dlouho daný faktor ovlivňuje cenu

| Indikátor | Frekvence | Tržní vliv | Doporučená váha | Zdůvodnění |
|-----------|-----------|------------|-----------------|------------|
| **Interest Rates** (ECB/Fed) | 6–8 týdnů | ⭐⭐⭐⭐⭐ | **0.22** | Největší single event pro EUR/USD |
| **Inflation** (CPI, PCE) | Měsíčně | ⭐⭐⭐⭐⭐ | **0.20** | Přímý driver ECB/Fed rozhodnutí |
| **GDP** | Čtvrtletně | ⭐⭐⭐⭐ | **0.13** | Silný signal, ale zastaralý – mění se pomalu |
| **Labor** (NFP, Unemployment) | Měsíčně | ⭐⭐⭐⭐ | **0.12** | Klíčový pro Fed, méně pro ECB |
| **COT Bias** | Týdně | ⭐⭐⭐⭐ | **0.11** | Pozice velkých hráčů – ideální pro swing |
| **SPMI** (Services PMI) | Měsíčně | ⭐⭐⭐ | **0.08** | Přední ukazatel – dobře predikuje |
| **MPMI** (Manufacturing PMI) | Měsíčně | ⭐⭐⭐ | **0.06** | Slabší dopad pro EUR/USD než SPMI |
| **Retail Sales** | Měsíčně | ⭐⭐⭐ | **0.05** | Důležité, ale sekundární |
| **Trend** | Denně | ⭐⭐ | **0.05** | Technický kontext fundamentu |
| **Retail Sentiment** | Kontinuálně | ⭐⭐ | **0.04** | Kontrariánský signál – **hodnocen obráceně!** |
| **Seasonality** | Měsíčně | ⭐ | **0.02** | Tiebreaker, ne driver |

> **Důležitá poznámka:** Tyto váhy jsou výchozí bod. Systém autoresearche je bude postupně automaticky přizpůsobovat na základě historické predikční přesnosti.

---

### 4. Potřebuješ AI nebo vzorce?

**Fáze 1 (launch):** Čistě vzorce + normalizace – deterministic, transparent, debugovatelný  
**Fáze 2 (autoresearch):** LLM + reinforcement learning pro auto-tuning vah  
**Fáze 3 (future):** Možné zapojení malého fine-tuned modelu

---

## 📁 ARCHITEKTURA PROJEKTU

```
eurusd-analyzer/
├── frontend/          # Next.js 14 + TailwindCSS
│   ├── app/
│   ├── components/
│   └── lib/
├── backend/           # Python FastAPI
│   ├── collectors/    # Data fetching ze zdrojů
│   ├── scoring/       # Normalizace + scoring engine
│   ├── prediction/    # Polymarket + predikční logika
│   ├── autoresearch/  # Karpathy AutoResearch adapter
│   └── scheduler/     # Cron jobs
├── database/          # Supabase schema + migrations
└── docs/
```

---

## 🗄️ DATABÁZE (Supabase / PostgreSQL)

### Schéma tabulek

```sql
-- Historická data každého indikátoru
CREATE TABLE indicator_readings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL,
  indicator_name TEXT NOT NULL,       -- 'cpi_us', 'nfp', 'ecb_rate' atd.
  pair TEXT NOT NULL DEFAULT 'EURUSD',
  actual FLOAT,
  forecast FLOAT,
  previous FLOAT,
  surprise FLOAT,                      -- actual - forecast
  surprise_zscore FLOAT,               -- normalizovaný surprise
  raw_score FLOAT,                     -- -3 až +3 (float, před váhou, bez zaokrouhlování)
  direction TEXT,                      -- 'USD_BULLISH' | 'EUR_BULLISH' | 'NEUTRAL'
  source TEXT,                         -- 'forex_factory' | 'cftc' | 'manual'
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Denní agregované skóre
CREATE TABLE daily_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL UNIQUE,
  pair TEXT NOT NULL DEFAULT 'EURUSD',
  
  -- Skóre jednotlivých indikátorů (posledně dostupná hodnota)
  score_interest_rates FLOAT,
  score_inflation FLOAT,
  score_gdp FLOAT,
  score_labor FLOAT,
  score_cot FLOAT,
  score_spmi FLOAT,
  score_mpmi FLOAT,
  score_retail_sales FLOAT,
  score_trend FLOAT,
  score_retail_sentiment FLOAT,
  score_seasonality FLOAT,
  
  -- Váhy použité tento den (mohou se měnit po autoresearch)
  weights JSONB,
  
  -- Výsledné skóre
  total_score FLOAT,                   -- vážený součet
  label TEXT,                          -- 'Strong Bullish', 'Bearish' atd.
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Predikce (7 dní dopředu)
CREATE TABLE predictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_date DATE NOT NULL,          -- kdy byla predikce vytvořena
  prediction_date DATE NOT NULL,       -- na který den predikuje
  pair TEXT NOT NULL DEFAULT 'EURUSD',
  
  predicted_score_low FLOAT,           -- spodní hranice zóny
  predicted_score_high FLOAT,         -- horní hranice zóny
  predicted_score_mid FLOAT,           -- střed
  confidence FLOAT,                    -- 0.0 - 1.0
  
  polymarket_probabilities JSONB,      -- raw data z Polymarketu
  upcoming_events JSONB,               -- jaké události se očekávají
  
  -- Vyhodnocení přesnosti (doplní se zpětně)
  actual_score FLOAT,                  -- doplní se po skutečném dni
  accuracy_score FLOAT,               -- jak přesná byla predikce
  
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Autoresearch log – záznamy o vylepšení vah
CREATE TABLE autoresearch_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_date DATE NOT NULL,
  old_weights JSONB,
  new_weights JSONB,
  improvement_notes TEXT,              -- co LLM navrhlo
  accuracy_before FLOAT,
  accuracy_after FLOAT,
  applied BOOLEAN DEFAULT FALSE,       -- jestli byly váhy aplikovány
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cache pro normalizační statistiky
CREATE TABLE normalization_stats (
  indicator_name TEXT PRIMARY KEY,
  lookback_days INT DEFAULT 365,
  mean_surprise FLOAT,
  std_surprise FLOAT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 📡 DATOVÉ ZDROJE A API

### 1. Forex Factory (CPI, NFP, Retail Sales, PMIs, Interest Rates, GDP)

```python
# Neoficiální, ale stabilní endpoint
FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
# Pro jiné týdny:
# https://nfs.faireconomy.media/ff_calendar_nextweek.json
# https://nfs.faireconomy.media/ff_calendar_thismonth.json (není vždy dostupný)

# Odpověď vypadá takto:
# [
#   {
#     "title": "CPI m/m",
#     "country": "USD",
#     "date": "2025-01-15T13:30:00-05:00",
#     "impact": "High",       ← vždy stejná pro daný event
#     "forecast": "0.3%",
#     "previous": "0.3%",
#     "actual": "0.4%"        ← null pokud ještě nevyšlo
#   }
# ]
```

**Odpověď na tvůj dotaz ohledně vah na FF:** `"impact": "High"` je vždy stejný pro stejný typ události – **nemění se**. Nemusíš se bát, že CPI bude jednou High a podruhé Medium. Co se mění je jen `actual` hodnota. Proto normalizujeme surprise přes z-score.

**Mapování FF eventů na tvoje indikátory:**

| Forex Factory event | Tvůj indikátor | Měna |
|--------------------|----------------|------|
| CPI m/m, CPI y/y, Core CPI | Inflation | USD + EUR |
| Non-Farm Payrolls, Unemployment Rate | Labor | USD |
| Advance GDP q/q, Flash GDP | GDP | USD + EUR |
| Fed Funds Rate, Main Refinancing Rate | Interest Rates | USD + EUR |
| Manufacturing PMI | MPMI | USD + EUR |
| Services PMI | SPMI | USD + EUR |
| Retail Sales m/m | Retail Sales | USD + EUR |

---

### 2. COT (Commitment of Traders) Data – Duální kontrakty

```python
# Sledujeme DVA kontrakty přes Nasdaq Data Link:
# 1) Euro FX (6E) – sentiment velkých hráčů přímo na EUR
# 2) US Dollar Index (DX) – sentiment na USD (invertovaný vůči EUR)

import nasdaqdatalink
nasdaqdatalink.ApiConfig.api_key = "TVUJ_KLIC"

cot_eur = nasdaqdatalink.get("CFTC/EUR_FO_L_ALL")  # Euro FX (6E)
cot_dxy = nasdaqdatalink.get("CFTC/DX_FO_L_ALL")   # US Dollar Index (DX)

# Vychází každý pátek (~15:30 ET), data za předchozí úterý
# Klíčová hodnota: Net Noncommercial = Long - Short spekulantů
```

**Kombinovaný COT Bias scoring:**
```python
def score_cot_combined(
    eur_net: float,       # Euro FX (6E) net noncommercial pozice
    dxy_net: float,       # DXY (DX) net noncommercial pozice
    eur_lookback: list,   # 52 týdnů EUR 6E dat
    dxy_lookback: list    # 52 týdnů DXY dat
) -> float:
    """
    Kombinuje oba kontrakty do jednoho COT Bias skóre.

    Logika:
    - High EUR net long + Low DXY net long = silný bullish EUR (+ skóre)
    - Low EUR net long + High DXY net long = silný bearish EUR (- skóre)

    Váhy: EUR (6E) = 60%, DXY = 40%
    DXY skóre je INVERTOVÁNO (high DXY long = bearish EUR)
    """
    # EUR 6E: percentil v 52týdenním okně → -3 až +3
    eur_pct = scipy.stats.percentileofscore(eur_lookback, eur_net)
    eur_score = (eur_pct / 100 * 6) - 3

    # DXY DX: percentil → invertován (high DXY net long = bearish EUR)
    dxy_pct = scipy.stats.percentileofscore(dxy_lookback, dxy_net)
    dxy_score = -((dxy_pct / 100 * 6) - 3)

    # Kombinace: EUR váha 60%, DXY váha 40%
    combined = (eur_score * 0.6) + (dxy_score * 0.4)
    return max(-3.0, min(3.0, combined))

# Příklady:
# EUR percentil 90% (+2.4) + DXY percentil 15% (inv: +2.1)
# → combined = (2.4*0.6) + (2.1*0.4) = 1.44 + 0.84 = +2.28 → Bullish
#
# EUR percentil 15% (-2.1) + DXY percentil 85% (inv: -2.1)
# → combined = (-2.1*0.6) + (-2.1*0.4) = -1.26 + (-0.84) = -2.10 → Bearish
```

---


### 3. Retail Sentiment (Obráceně!)

```python
# Option A: OANDA fxTrade API (bezplatný developer account)
# Poskytuje "open interest" a "long/short ratio" pro retailové klienty
OANDA_SENTIMENT_URL = "https://api-fxtrade.oanda.com/v3/instruments/EUR_USD/orderBook"
# Headers: {"Authorization": "Bearer TVUJ_TOKEN"}

# Option B: MyFXBook Community Outlook (scraping – nestabilní)
# Option C: Myfxbook API (vyžaduje account)

# Scoring – OBRÁCENĚ:
def score_retail_sentiment(long_pct: float) -> float:
    """
    Retail je typicky wrong-way trader.
    long_pct = 80% long → trh pravděpodobně půjde dolů → bearish → záporné skóre
    """
    neutral_zone = 50.0
    deviation = long_pct - neutral_zone  # +30 pokud 80% long
    # Čím více retailu long, tím více bearish signál
    # Škálování: každých ~17% odchylky = 1 bod (50% → ±3 max)
    raw = -(deviation / 16.67)
    return max(-3.0, min(3.0, raw))  # pouze clamp, žádné zaokrouhlování
```

---

### 4. Seasonality

```python
# Není žádná API – počítáme historicky sami
# Princip: průměrná denní/měsíční změna EUR/USD za posledních 10+ let pro daný měsíc/týden

# Data pro výpočet: OANDA API nebo Alpha Vantage (historické OHLC)
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
# Parametry: function=FX_DAILY, from_symbol=EUR, to_symbol=USD
# Bezplatný tier: 25 req/den (stačí pro denní update)

def calculate_seasonality(month: int, historical_returns: pd.DataFrame) -> float:
    """
    Průměrný return EUR/USD v daném měsíci za posledních 10 let.
    Normalizovat na škálu -3 až +3 (float, bez zaokrouhlování).
    """
    monthly_returns = historical_returns[historical_returns.index.month == month]['return']
    avg_return = monthly_returns.mean()
    # Normalizace z-score, pak clamp na -3.0..+3.0
    z = avg_return / historical_returns['return'].std()
    return max(-3.0, min(3.0, z))  # pouze clamp, žádné zaokrouhlování
```

---

### 5. Trend

```python
# Čistě technický – bereme z price dat
# Používáme kombinaci: EMA 20, EMA 50, ADX

def calculate_trend_score(daily_ohlc: pd.DataFrame) -> float:
    """
    EMA20 vs EMA50: směr trendu
    ADX > 25: silný trend
    RSI: momentum
    """
    ema20 = daily_ohlc['close'].ewm(span=20).mean().iloc[-1]
    ema50 = daily_ohlc['close'].ewm(span=50).mean().iloc[-1]
    current_price = daily_ohlc['close'].iloc[-1]
    
    # Trend směr + síla (ADX modifikátor)
    # adx = calculate_adx(daily_ohlc)  # 0-100, >25 = silný trend
    if ema20 > ema50 and current_price > ema20:
        base_score = 2.5  # bullish EUR
    elif ema20 < ema50 and current_price < ema20:
        base_score = -2.5  # bearish EUR
    else:
        base_score = 0.0

    # Síla trendu (ADX modifikátor) – škáluje base_score bez zaokrouhlování
    # adx_factor = min(adx / 25.0, 1.2)  # >25 = plná síla, max 1.2×
    # base_score *= adx_factor
    return max(-3.0, min(3.0, base_score))  # clamp, žádné zaokrouhlování
```

---

### 6. Polymarket API (Predikce)

```python
# Gamma API – bezplatné, bez autentizace
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"

# Najít relevantní markety (CPI, GDP, Fed decision, ECB decision)
markets = requests.get(f"{POLYMARKET_GAMMA}/markets", params={
    "tag": "economics",
    "active": True,
    "limit": 50
})

# Příklad market pro Fed decision:
# GET /markets?tag=fed-funds-rate&active=true
# Vrátí: {"question": "Will Fed cut rates in January?", "outcomePrices": ["0.23", "0.77"]}
# outcomePrices[0] = pravděpodobnost YES (0.0 - 1.0)

# Mapování na tvůj scoring systém:
def polymarket_to_score(yes_probability: float, event_type: str) -> float:
    """
    Převede Polymarket pravděpodobnost na bullish/bearish implikaci.
    event_type určí zda 'Yes' je bullish nebo bearish pro EUR.
    """
    # Příklad: "Will ECB cut rates?" → Yes = bearish EUR
    # Příklad: "Will US CPI beat forecast?" → Yes = bullish USD = bearish EUR
    pass
```

---

## ⏰ AKTUALIZAČNÍ HARMONOGRAM

### Kdy spouštět denní update?

Po analýze časů vydávání dat doporučuji: **20:00 UTC (22:00 CEST)**

Zdůvodnění:
- Většina US dat vychází v 13:30–15:00 UTC → do 19:00 jsou zpracovány
- ECB/EU data vychází 09:00–10:00 UTC → jsou také zahrnuty
- Fed/ECB speeches typicky končí do 18:00 UTC
- Polymarket ceny jsou po close nejstabilnější

### Aktualizační proces (pseudokód)

```python
# scheduler/daily_update.py – spouštět každý den v 19:00 UTC

async def daily_update(today: date):
    # KROK 1: Sběr dat pro dnešní den
    ff_events = await fetch_forex_factory_today()
    cot_data = await fetch_cot_weekly()  # pouze v pátek nová data
    sentiment = await fetch_retail_sentiment()
    trend_score = await calculate_trend()
    seasonality = await calculate_seasonality(today.month)
    
    # KROK 2: Normalizace + scoring každého indikátoru
    scores = calculate_all_scores(ff_events, cot_data, sentiment, trend_score, seasonality)
    
    # KROK 3: Vážený součet → daily_scores tabulka
    weights = await get_current_weights()  # může být upraveno autoresearchem
    total = weighted_sum(scores, weights)
    await save_daily_score(today, scores, total)
    
    # KROK 4: Porovnat dnešní skóre s včerejší predikcí na dnešek
    yesterday_prediction = await get_prediction(created_date=today-1, prediction_date=today)
    if yesterday_prediction:
        accuracy = calculate_accuracy(total, yesterday_prediction)
        await save_accuracy(yesterday_prediction.id, total, accuracy)
    
    # KROK 5: Spustit autoresearch pokud máme 7+ nových accuracy dat pointů
    if should_run_autoresearch(today):
        await run_autoresearch()
    
    # KROK 6: Smazat data starší než 30 dní (rolling window)
    await delete_old_data(cutoff=today - timedelta(days=30))
    
    # KROK 7: Generovat novou predikci na následujících 7 dní
    upcoming_events = await fetch_upcoming_events(days=7)
    polymarket_signals = await fetch_polymarket_signals(upcoming_events)
    new_prediction = await generate_7day_prediction(
        current_score=total,
        upcoming_events=upcoming_events,
        polymarket_data=polymarket_signals
    )
    await save_predictions(new_prediction)
    
    # KROK 8: Porovnat novou predikci s předchozí 7denní predikcí
    prev_prediction = await get_prediction(created_date=today-1, days_range=7)
    prediction_drift = compare_predictions(new_prediction, prev_prediction)
    await log_prediction_drift(prediction_drift)
```

---

## 🤖 AUTORESEARCH SYSTÉM (Karpathy-inspired)

### Jak to funguje

Karpathy's NanoAutoResearch princip: AI agent iterativně experimentuje, hodnotí výsledky, a navrhuje vylepšení kódu/parametrů bez lidského zásahu.

**Adaptace na tvůj projekt:**

```python
# autoresearch/weight_optimizer.py

AUTORESEARCH_SYSTEM_PROMPT = """
Jsi expert na forex fundamentální analýzu. Tvým úkolem je analyzovat
predikční přesnost systému a navrhnout optimalizaci vah indikátorů.

Dostaneš:
1. Aktuální váhy každého indikátoru
2. Historii predikcí za posledních 30 dní
3. Skutečné hodnoty skóre
4. Accuracy metriky

Na základě analýzy:
- Identifikuj které indikátory predikují nejpřesněji
- Navrhni nové váhy (musí dát součet 1.0)
- Zdůvodni každou změnu
- Vrať JSON s novými vahami a zdůvodněním

FORMÁT ODPOVĚDI (pouze JSON):
{
  "new_weights": {"interest_rates": 0.22, ...},
  "reasoning": "...",
  "expected_improvement": "...",
  "confidence": 0.0-1.0
}
"""

async def run_autoresearch():
    # Načíst historická data
    history = await get_last_30_days_accuracy()
    current_weights = await get_current_weights()
    
    # Volání Claude API
    response = await anthropic_client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        system=AUTORESEARCH_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"""
            Aktuální váhy: {json.dumps(current_weights)}
            
            Historie predikcí (posledních 30 dní):
            {format_prediction_history(history)}
            
            Accuracy statistiky:
            - Průměrná odchylka predikce: {history.mean_error:.2f}
            - Nejpřesnější indikátory: {get_top_predictors(history)}
            - Nejméně přesné indikátory: {get_worst_predictors(history)}
            
            Navrhni optimalizaci vah.
            """
        }]
    )
    
    new_weights = json.loads(response.content[0].text)
    
    # Ulož návrh – nevkládej automaticky, nejdříve loguj a ověř
    await save_autoresearch_log(
        old_weights=current_weights,
        new_weights=new_weights["new_weights"],
        notes=new_weights["reasoning"],
        applied=False  # admin potvrdí nebo automaticky po N dnech
    )
    
    # Automatická aplikace pokud confidence > 0.8 a improvement > 5%
    if new_weights["confidence"] > 0.8:
        await apply_new_weights(new_weights["new_weights"])
```

### GitHub repozitář pro referenci
- Karpathy NanoAutoResearch: `https://github.com/karpathy/nanoAutoResearch` (nebo ekvivalent)
- Implementace bude custom – základní princip: **run → evaluate → propose improvement → apply → repeat**

---

## 🎨 UI/UX DESIGN

### Technologie
- **Framework:** Next.js 14 (App Router)
- **Styling:** TailwindCSS + shadcn/ui
- **Grafy:** Recharts nebo TradingView Lightweight Charts
- **Tmavý motiv:** Primárně, bez možnosti přepnutí (je to trading app)

### Barevná paleta
```css
:root {
  --bg-primary: #0a0a0f;
  --bg-card: #111118;
  --bg-elevated: #1a1a24;
  --accent-bullish: #22d3a0;     /* zelená */
  --accent-bearish: #f43f5e;     /* červená */
  --accent-neutral: #6b7280;
  --accent-prediction: #f59e0b;  /* žlutá pro predikci (tečkovaná) */
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --border: #1e293b;
}
```

### Komponenty

#### Score Overview (Foto 1 styl)
```
┌─────────────────────────────────────────────┐
│ Score Overview                    EUR/USD    │
│ ─────────────────────────────────────────── │
│ COT BIAS          -1  │  GDP          -2.0 │
│ ████░░░░░░ bearish       │  ██████████ bear  │
│                          │                  │
│ Inflation         +1   │  Interest Rates  0│
│ ░░░░░█████ bullish       │  ░░░░░░░░░░ neut │
│ ...                                          │
│ ─────────────────────────────────────────── │
│ TOTAL WEIGHTED SCORE: -2  🟠 Bearish       │
└─────────────────────────────────────────────┘
```

#### Score History Chart (Foto 2 styl)
```
Komponenty grafu:
- Žlutá linka: historické denní skóre (30 dní dozadu)
- Tečkovaná žlutá: predikce (7 dní dopředu)
- Červená zóna (2 linky): predikční interval (low-high)
- Badge vpravo nahoře: změna za 24h (jako na foto)
- Tlačítka: 1W | 1M | 3M (3M = disabled v MVP)
- Osa Y: -3 až +3 (celá čísla, odpovídá škále skórování)
```

#### Events Upcoming Panel
```
┌──────────────────────────────────────────────┐
│ Upcoming Events (7 days)                     │
│ ────────────────────────────────────────────│
│ 📅 Tue 15 Jan  13:30  🔴 US CPI m/m         │
│    Forecast: 0.3%  │  Polymarket YES: 34%   │
│                                              │
│ 📅 Thu 17 Jan  12:45  🔴 ECB Rate Decision  │
│    Forecast: Hold  │  Polymarket Cut: 12%   │
└──────────────────────────────────────────────┘
```

---

## 🔧 TECH STACK

| Vrstva | Technologie | Zdůvodnění |
|--------|------------|------------|
| Frontend | Next.js 14 + TypeScript | SSR, API routes |
| Styling | TailwindCSS + shadcn/ui | Rychlé tmavé UI |
| Grafy | TradingView Lightweight Charts | Profesionální look |
| Backend | Python FastAPI | Ideální pro data science |
| Scheduler | APScheduler (Python) | Cron v rámci FastAPI |
| Databáze | Supabase (PostgreSQL) | Realtime + REST + bezplatný tier |
| AI/LLM | Anthropic Claude API | Autoresearch + scoring assistance |
| Hosting | Vercel (FE) + Railway/Render (BE) | Bezplatné tiery dostačují |
| Cache | Redis (Upstash – free tier) | Cache FF dat, rate limiting |

---

## 🔑 API KLÍČE KTERÉ BUDEŠ POTŘEBOVAT

| Služba | Kde získat | Cena |
|--------|-----------|------|
| Nasdaq Data Link (COT) | data.nasdaq.com | Zdarma |
| Alpha Vantage (Price data) | alphavantage.co | Zdarma (25 req/den) |
| OANDA API (Sentiment + Price) | developer.oanda.com | Zdarma (demo účet stačí) |
| Anthropic API (Autoresearch) | console.anthropic.com | ~$0.01-0.05/den |
| Polymarket Gamma API | gamma-api.polymarket.com | Zdarma, bez klíče |
| Supabase | supabase.com | Zdarma tier |
| Forex Factory | nfs.faireconomy.media | Zdarma, bez klíče |

---

## 📋 DEVELOPMENT ROADMAP

### Fáze 0: Setup (1-2 dny)
- [ ] Supabase projekt + schema migrace
- [ ] Python FastAPI projekt skeleton
- [ ] Next.js projekt + tmavý theme
- [ ] Environment variables setup

### Fáze 1: Data Collectors (3-5 dní)
- [ ] Forex Factory collector + normalizace
- [ ] COT collector (Nasdaq Data Link)
- [ ] OANDA sentiment collector
- [ ] Alpha Vantage price + trend výpočet
- [ ] Seasonality kalkulátor
- [ ] Polymarket market finder + signal extractor

### Fáze 2: Scoring Engine (2-3 dny)
- [ ] Normalizace surprise → z-score
- [ ] Mapování z-score → -5 až +5 scale
- [ ] Retail sentiment inverted scoring
- [ ] Weighted sum kalkulátor
- [ ] Historická normalizace stats (seed data)

### Fáze 3: Scheduler (1-2 dny)
- [ ] APScheduler setup (19:00 UTC daily)
- [ ] Full pipeline test
- [ ] Logging + error handling

### Fáze 4: Predikce (2-3 dny)
- [ ] Polymarket event matcher (upcoming events → markets)
- [ ] 7-day prediction generator
- [ ] Predikční zóna kalkulace (confidence interval)
- [ ] Accuracy tracking systém

### Fáze 5: Frontend (3-5 dní)
- [ ] Score Overview tabulka (foto 1 styl)
- [ ] Score History chart (foto 2 styl – žlutá + zóna)
- [ ] Upcoming Events panel
- [ ] Accuracy / Autoresearch log panel

### Fáze 6: Autoresearch (2-3 dny)
- [ ] Claude API integration
- [ ] Weight optimizer prompt engineering
- [ ] Auto-apply logika
- [ ] A/B tracking (starý vs nový weight)

### Fáze 7: Testing & Backtesting (ongoing)
- [ ] Seed historická data (posledních 6 měsíců)
- [ ] Backtest scoring systému
- [ ] Accuracy validace

---

## ❓ OTÁZKY KTERÉ POTŘEBUJI ZODPOVĚDĚT

Pro finalizaci plánu potřebuji vědět:

1. **COT data:** Chceš sledovat pouze EUR/USD speculative pozice, nebo také USD Index (DXY) COT? Oboje dohromady dává lepší obrázek.

2. **GDP scoring:** GDP vychází jednou za čtvrt roku. Chceš skóre "zmrazit" na 3 měsíce a aktualizovat při novém vydání, nebo používat předběžné odhady (Flash GDP)?

3. **Interest Rates:** Chceš sledovat jen skutečná rozhodnutí (ECB/Fed meetings), nebo i forward guidance a speeches (hawkish/dovish language)? To druhé by vyžadovalo NLP analýzu projevů.

4. **Autoresearch automatizace:** Chceš, aby systém automaticky aplikoval nové váhy (po splnění podmínek confidence), nebo chceš vždy ručně schválit? Doporučuji hybridní: auto-apply po 14+ dnech dat s confidence > 0.85.

5. **Přístup:** Bude to jen pro tebe, nebo pro více uživatelů? (Ovlivňuje auth systém)

6. **Polymarket dostupnost:** Polymarket má markety hlavně na velké US události (Fed, CPI). Pro ECB a EU data je pokrytí slabší. Je to pro tebe OK, nebo chceš fallback (např. predikce bez Polymarketu pro EU eventy)?

7. **Backtesting:** Chceš backtest funkci kde si zadáš datum a systém ti ukáže jak by to hodnotil historicky? Nebo stačí rolling 30 dní?

8. **Hosting:** Máš preferenci kde hostovat backend (Railway, Render, VPS)?

9. **Notifikace:** Chceš push/email notifikace když se skóre změní o více než X bodů?

10. **Manuální override:** Chceš možnost ručně upravit skóre jednoho indikátoru (např. po nečekaném speech ECB presidenta mimo calendar)?

---

## ⚠️ RIZIKA A LIMITACE

| Riziko | Závažnost | Řešení |
|--------|-----------|--------|
| Forex Factory neoficiální API může být nedostupné | Střední | Fallback: scraping + cache posledních hodnot |
| Polymarket nemá EU eventy | Střední | Použít jen US Polymarket data jako proxy + fallback na statistiku |
| COT data jsou s 3-4 dny zpožděním | Nízká | Přijatelné pro swing trading |
| Autoresearch může přeoptimalizovat (overfitting) | Vysoká | Min. 30 data pointů před aplikací, max. ±20% změna váhy na jeden run |
| Alpha Vantage limit 25 req/den | Nízká | 1 request/den pro EURUSD daily data stačí |
| Normalizace z-score vyžaduje historická data | Střední | Seedovat databázi s min. 1 rokem dat při deployi |

---

*Dokument vytvořen pro Antigravity AI programming assistant*  
*Verze: 1.0 | Datum: 2025*  
*Projekt: EUR/USD Fundamental Analyzer & Predictor*

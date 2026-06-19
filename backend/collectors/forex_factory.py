import httpx
from datetime import datetime, timezone
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel

# Konstanty
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

class FFEvent(BaseModel):
    title: str
    country: str
    date: datetime
    impact: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    indicator_key: Optional[str] = None

# Mapování názvů z Forex Factory na naše interní klíče indikátorů
# Porovnávání probíhá přes `key.lower() in title.lower()` — stačí substring.
TITLE_TO_INDICATOR = {
    # ── INFLATION ────────────────────────────────────────────────────────
    "CPI m/m":                       "cpi",
    "Core CPI m/m":                  "cpi",
    "CPI y/y":                       "cpi",
    "Core CPI y/y":                  "cpi",
    "Tokyo Core CPI y/y":            "cpi",
    "National Core CPI y/y":         "cpi",
    "Core PCE Price Index m/m":      "pce",
    "PCE Price Index m/m":           "pce",
    "PCE Price Index y/y":           "pce",
    "PPI m/m":                       "cpi",
    "Core PPI m/m":                  "cpi",
    "PPI y/y":                       "cpi",
    "Core PCE Price Index":          "pce",
    "PCE Price Index":               "pce",
    "Import Prices m/m":             "cpi",

    # ── LABOR ─────────────────────────────────────────────────────────────
    "Non-Farm Employment Change":    "nfp",
    "Unemployment Rate":             "unemployment",
    "ADP Non-Farm Employment":       "nfp",
    "JOLTS Job Openings":            "nfp",
    "Initial Jobless Claims":        "unemployment",
    "Continuing Jobless Claims":     "unemployment",
    "Average Hourly Earnings":       "nfp",
    "Claimant Count Change":         "unemployment",
    "Employment Change":             "nfp",
    "Participation Rate":            "unemployment",

    # ── GDP / AKTIVITA ───────────────────────────────────────────────────
    "Advance GDP q/q":               "gdp_flash",
    "Flash GDP q/q":                 "gdp_flash",
    "Prelim GDP q/q":                "gdp_flash",
    "Second Estimate GDP":           "gdp_flash",
    "Final GDP q/q":                 "gdp_flash",
    "GDP q/q":                       "gdp_flash",
    "Trade Balance":                 "gdp_flash",
    "Current Account":               "gdp_flash",
    "German ZEW Economic Sentiment": "gdp_flash",
    "ZEW Economic Sentiment":        "gdp_flash",
    "German Ifo Business Climate":   "gdp_flash",
    "Ifo Business Climate":          "gdp_flash",

    # ── MANUFACTURING PMI ────────────────────────────────────────────────
    "Flash Manufacturing PMI":       "mpmi",
    "ISM Manufacturing PMI":         "mpmi",
    "Manufacturing PMI":             "mpmi",
    "Chicago PMI":                   "mpmi",
    "Empire State Manufacturing":    "mpmi",
    "Philly Fed Manufacturing":      "mpmi",
    "Philadelphia Fed":              "mpmi",

    # ── SERVICES PMI ─────────────────────────────────────────────────────
    "Flash Services PMI":            "spmi",
    "ISM Services PMI":              "spmi",
    "Services PMI":                  "spmi",
    "Flash Composite PMI":           "spmi",
    "Composite PMI":                 "spmi",

    # ── RETAIL SALES ─────────────────────────────────────────────────────
    "Retail Sales m/m":              "retail_sales",
    "Core Retail Sales m/m":         "retail_sales",
    "Retail Sales y/y":              "retail_sales",

    # ── INTEREST RATES / CB ──────────────────────────────────────────────
    # Plně specifické názvy CB → přímý rate klíč
    "Federal Funds Rate":            "fed_rate",
    "Main Refinancing Rate":         "ecb_rate",
    "Deposit Facility Rate":         "ecb_rate",
    "FOMC Statement":                "fed_rate",
    "FOMC Press Conference":         "fed_rate",
    "FOMC Meeting Minutes":          "fed_rate",
    "ECB Press Conference":          "ecb_rate",
    "ECB Meeting Accounts":          "ecb_rate",
    "ECB President":                 "ecb_rate",
    "Fed Chair":                     "fed_rate",
    "Official Bank Rate":            "boe_rate",
    "BOE Monetary Policy Report":    "boe_rate",
    "MPC Official Bank Rate Votes":  "boe_rate",
    "BOE Gov":                       "boe_rate",
    "BOJ Policy Rate":               "boj_rate",
    "BOJ Press Conference":          "boj_rate",
    "BOJ Gov":                       "boj_rate",
    "Official Cash Rate":            "rbnz_rate",
    "RBNZ Rate Statement":           "rbnz_rate",
    "RBNZ Gov":                      "rbnz_rate",
    "RBNZ Press Conference":         "rbnz_rate",
    # Generické názvy → "rate_decision" sentinel; country určí správný rate klíč dynamicky
    # Takové názvy používá např. BoC, RBA a další CB které nemáme explicitně pojmenované
    "Monetary Policy Statement":     "rate_decision",
    "Rate Statement":                "rate_decision",
    "Interest Rate Decision":        "rate_decision",
    "Monetary Policy Summary":       "rate_decision",
}

# Mapování country kódu na příslušný rate klíč (CB dané země)
# Používá se pro resolvání generického sentinelu "rate_decision"
COUNTRY_TO_RATE_KEY = {
    "USD": "fed_rate",
    "EUR": "ecb_rate",
    "GBP": "boe_rate",
    "JPY": "boj_rate",
    "NZD": "rbnz_rate",
    "AUD": "rba_rate",
    "CAD": "boc_rate",
    "XAU": "xau_rate",
}

# Všechny rate klíče — tyto indikátory NEDOSTANOU country suffix
# (narozdíl od běžných indikátorů jako cpi_us, nfp_eu, atd.)
ALL_RATE_KEYS = set(COUNTRY_TO_RATE_KEY.values())
def map_ff_title_to_indicator(title: str) -> Optional[str]:
    """Snaží se přiřadit název z Forex Factory k našemu internímu indikátoru."""
    for key, indicator in TITLE_TO_INDICATOR.items():
        if key.lower() in title.lower():
            return indicator
    return None

from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def fetch_forex_factory_week(pair: str = "EURUSD") -> List[FFEvent]:
    """
    Stáhne JSON kalendář z Forex Factory pro tento týden.
    Vyfiltruje jen měny z daného páru s High/Medium dopadem.
    """
    base = pair[:3]
    quote = pair[3:]
    allowed_countries = [base, quote]
    
    logger.info(f"Fetching Forex Factory calendar for {pair} ({allowed_countries})...")
    
    events = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(FF_URL)
            response.raise_for_status()
            data = response.json()
            
            for item in data:
                country = item.get("country", "")
                impact = item.get("impact", "")
                
                # Zajímají nás jen base a quote s High/Medium dopadem
                if country not in allowed_countries or impact not in ["High", "Medium"]:
                    continue
                
                title = item.get("title", "")
                # Zkusíme namapovat
                indicator_key = map_ff_title_to_indicator(title)
                if indicator_key:
                    if indicator_key == "rate_decision":
                        # Generický CB event — určíme správný rate klíč podle country
                        resolved = COUNTRY_TO_RATE_KEY.get(country)
                        if resolved:
                            indicator_key = resolved
                            logger.debug(f"rate_decision [{country}] → {indicator_key}")
                        else:
                            indicator_key = None  # neznámá CB — přeskočíme
                    elif indicator_key not in ALL_RATE_KEYS:
                        # Běžný (ne-rate) indikátor: přidej country suffix
                        if country == "USD":
                            suffix = "us"
                        elif country == "EUR":
                            suffix = "eu"
                        elif country == "GBP":
                            suffix = "uk"
                        else:
                            suffix = country.lower()
                        indicator_key = f"{indicator_key}_{suffix}"
                    # Pokud je indicator_key v ALL_RATE_KEYS (fed_rate, boj_rate, rbnz_rate...)
                    # → ponecháme beze změny (bez suffixu)
                
                # Zpracování data (očekávaný formát: 2025-01-15T13:30:00-05:00)
                date_str = item.get("date", "")
                try:
                    event_date = datetime.fromisoformat(date_str)
                except ValueError:
                    logger.warning(f"Nepodařilo se naparsovat datum z FF: {date_str}")
                    continue
                
                event = FFEvent(
                    title=title,
                    country=country,
                    date=event_date,
                    impact=impact,
                    forecast=item.get("forecast") or None,
                    previous=item.get("previous") or None,
                    actual=item.get("actual") or None,
                    indicator_key=indicator_key
                )
                events.append(event)
                
    except Exception as e:
        logger.error(f"Error fetching Forex Factory data: {e}")
        # Tady by mohl přijít fallback na parsování HTML
        
    return events

def filter_today_events(events: List[FFEvent]) -> List[FFEvent]:
    """
    Vyfiltruje z týdenního seznamu události jen pro dnešní den.
    
    Používá UTC datum konzistentně — Railway server běží v UTC.
    Forex Factory vrací timestampy s timezone offsetem (např. -05:00),
    které konvertujeme do UTC před porovnáním data.
    """
    today_utc = datetime.now(timezone.utc).date()
    result = []
    for e in events:
        if e.date.tzinfo is not None:
            # Timezone-aware datetime — správně převedem do UTC
            event_date_utc = e.date.astimezone(timezone.utc).date()
        else:
            # Naive datetime (bez timezone info) — považujeme za UTC
            event_date_utc = e.date.date()
        if event_date_utc == today_utc:
            result.append(e)
    return result

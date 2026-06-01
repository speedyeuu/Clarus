import httpx
from datetime import datetime
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
    "CPI y/y":                       "cpi",
    "Core CPI m/m":                  "cpi",
    "Core CPI y/y":                  "cpi",
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
    "Federal Funds Rate":            "fed_rate",
    "Main Refinancing Rate":         "ecb_rate",
    "Deposit Facility Rate":         "ecb_rate",
    "Monetary Policy Statement":     "fed_rate",  # speech/statement
    "FOMC Statement":                "fed_rate",
    "Rate Statement":                "fed_rate",
    "ECB Press Conference":          "ecb_rate",
    "FOMC Press Conference":         "fed_rate",
    "FOMC Meeting Minutes":          "fed_rate",
    "ECB Meeting Accounts":          "ecb_rate",
    "Fed Chair":                     "fed_rate",
    "ECB President":                 "ecb_rate",
}

def map_ff_title_to_indicator(title: str) -> Optional[str]:
    """Snaží se přiřadit název z Forex Factory k našemu internímu indikátoru."""
    for key, indicator in TITLE_TO_INDICATOR.items():
        if key.lower() in title.lower():
            return indicator
    return None

async def fetch_forex_factory_week() -> List[FFEvent]:
    """
    Stáhne JSON kalendář z Forex Factory pro tento týden.
    Vyfiltruje jen EUR a USD s High/Medium dopadem.
    """
    logger.info("Fetching Forex Factory calendar from unofficial JSON API...")
    
    events = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(FF_URL)
            response.raise_for_status()
            data = response.json()
            
            for item in data:
                country = item.get("country", "")
                impact = item.get("impact", "")
                
                # Zajímají nás jen EUR/USD a High/Medium dopad
                if country not in ["USD", "EUR"] or impact not in ["High", "Medium"]:
                    continue
                
                title = item.get("title", "")
                # Zkusíme namapovat
                indicator_key = map_ff_title_to_indicator(title)
                if indicator_key:
                    if indicator_key not in ["fed_rate", "ecb_rate"]:
                        suffix = "us" if country == "USD" else "eu"
                        indicator_key = f"{indicator_key}_{suffix}"
                
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

async def filter_today_events(events: List[FFEvent]) -> List[FFEvent]:
    """Vyfiltruje z týdenního seznamu události jen pro dnešní den."""
    today = datetime.now().date()
    return [e for e in events if e.date.date() == today]

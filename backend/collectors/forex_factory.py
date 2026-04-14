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
    "CPI m/m":                       "inflation",
    "CPI y/y":                       "inflation",
    "Core CPI m/m":                  "inflation",
    "Core CPI y/y":                  "inflation",
    "PPI m/m":                       "inflation",
    "Core PPI m/m":                  "inflation",
    "PPI y/y":                       "inflation",
    "Core PCE Price Index":          "inflation",
    "PCE Price Index":               "inflation",
    "Import Prices m/m":             "inflation",

    # ── LABOR ─────────────────────────────────────────────────────────────
    "Non-Farm Employment Change":    "labor",
    "Unemployment Rate":             "labor",
    "ADP Non-Farm Employment":       "labor",
    "JOLTS Job Openings":            "labor",
    "Initial Jobless Claims":        "labor",
    "Continuing Jobless Claims":     "labor",
    "Average Hourly Earnings":       "labor",
    "Claimant Count Change":         "labor",
    "Employment Change":             "labor",
    "Participation Rate":            "labor",

    # ── GDP / AKTIVITA ───────────────────────────────────────────────────
    "Advance GDP q/q":               "gdp",
    "Flash GDP q/q":                 "gdp",
    "Prelim GDP q/q":                "gdp",
    "Second Estimate GDP":           "gdp",
    "Final GDP q/q":                 "gdp",
    "GDP q/q":                       "gdp",
    "Trade Balance":                 "gdp",
    "Current Account":               "gdp",
    "German ZEW Economic Sentiment": "gdp",
    "ZEW Economic Sentiment":        "gdp",
    "German Ifo Business Climate":   "gdp",
    "Ifo Business Climate":          "gdp",

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
    "Federal Funds Rate":            "interest_rates",
    "Main Refinancing Rate":         "interest_rates",
    "Deposit Facility Rate":         "interest_rates",
    "Monetary Policy Statement":     "interest_rates",
    "FOMC Statement":                "interest_rates",
    "Rate Statement":                "interest_rates",
    "ECB Press Conference":          "interest_rates",
    "FOMC Press Conference":         "interest_rates",
    "FOMC Meeting Minutes":          "interest_rates",
    "ECB Meeting Accounts":          "interest_rates",
    "Fed Chair":                     "interest_rates",
    "ECB President":                 "interest_rates",
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

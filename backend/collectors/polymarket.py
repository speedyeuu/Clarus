import httpx
from loguru import logger
import urllib.parse
from typing import Optional
from pydantic import BaseModel
import json

class PolymarketMarket(BaseModel):
    title: str
    yes_probability: float
_cached_markets = None

async def fetch_polymarket_economics() -> list[PolymarketMarket]:
    """
    Stahne aktivní trhy z Polymarketu, které se týkají makroekonomiky.
    Využívá vyhledávací endpoint /public-search s klíčovými slovy.
    Vrací seznam relevantních trhů a jejich 'Yes' pravděpodobnosti (implikovaných cen).
    """
    global _cached_markets
    if _cached_markets is not None:
        return _cached_markets

    keywords = ["fed", "cpi", "gdp", "jobless claims", "nfp", "payrolls", "ecb", "inflation", "unemployment", "rate"]
    search_terms = ["fed", "cpi", "gdp", "jobless", "nfp", "ecb", "inflation", "unemployment"]
    results = []
    seen_ids = set()

    logger.info("Fetching macro markets from Polymarket via /public-search...")
    
    for term in search_terms:
        url = "https://gamma-api.polymarket.com/public-search"
        params = {"q": term}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch search term '{term}' from Polymarket: {resp.status_code}")
                    continue
                data = resp.json()
                events = data.get("events", [])
                
                for ev in events:
                    markets = ev.get("markets", [])
                    for m in markets:
                        m_id = m.get("id")
                        if m_id in seen_ids:
                            continue
                        
                        # Zajímají nás pouze aktivní trhy
                        is_active = m.get("active")
                        is_closed = m.get("closed")
                        if str(is_active).lower() != "true" or str(is_closed).lower() == "true":
                            continue
                            
                        # Vyřazení trhů s nízkou likviditou (< $1,000 USD equivalent)
                        liquidity_val = m.get("liquidityNum") or m.get("liquidity") or 0.0
                        try:
                            if float(liquidity_val) < 1000.0:
                                continue
                        except (ValueError, TypeError):
                            pass
                            
                        question = m.get("question", "").lower()
                        # Zajímají nás pouze makro trhy z výše uvedených slov
                        if any(kw in question for kw in keywords):
                            outcomes_raw = m.get("outcomes", [])
                            outcomePrices_raw = m.get("outcomePrices", [])
                            
                            # Ošetření, pokud jsou pole vrácena jako JSON-encoded stringy (typické pro Gamma API)
                            if isinstance(outcomes_raw, str):
                                try:
                                    outcomes = json.loads(outcomes_raw)
                                except Exception:
                                    outcomes = []
                            else:
                                outcomes = outcomes_raw

                            if isinstance(outcomePrices_raw, str):
                                try:
                                    outcomePrices = json.loads(outcomePrices_raw)
                                except Exception:
                                    outcomePrices = []
                            else:
                                outcomePrices = outcomePrices_raw
                            
                            try:
                                yes_idx = outcomes.index("Yes")
                                yes_prob = float(outcomePrices[yes_idx])
                                
                                results.append(PolymarketMarket(
                                    title=m.get("question", ""),
                                    yes_probability=yes_prob
                                ))
                                seen_ids.add(m_id)
                            except (ValueError, IndexError):
                                # Pokud trh nemá "Yes", přeskočíme
                                continue
        except Exception as e:
            logger.warning(f"Error fetching Polymarket search term '{term}': {e}")
            
    _cached_markets = results
    return results

def extract_signal_from_polymarket(event_title: str, markets: list[PolymarketMarket]) -> Optional[float]:
    """
    Snaží se najít a extrahovat pravděpodobnost pro konkrétní událost
    na základě klíčových slov z názvu události z FF.
    """
    if not markets or not event_title:
        return None
        
    title_lower = event_title.lower()
    
    # Namapujeme si nejčastější FF názvy na klíčová slova Polymarketu
    keywords = []
    if "cpi" in title_lower or "inflation" in title_lower:
        keywords = ["cpi", "inflation"]
    elif "non-farm" in title_lower or "nfp" in title_lower or "employment" in title_lower:
        keywords = ["nfp", "nonfarm", "payrolls"]
    elif "gdp" in title_lower:
        keywords = ["gdp"]
    elif "rate" in title_lower and ("fed" in title_lower or "fomc" in title_lower):
        keywords = ["fed", "rate", "cut"]
    elif "jobless claims" in title_lower:
        keywords = ["jobless claims"]
        
    if not keywords:
        return None
        
    # Nyní vyhledáme nejlepší trh z polymarketu
    for m in markets:
        m_title = m.title.lower()
        # Pokud se aspoň 2 slova (nebo zásadní slova) shodují
        matching_kws = [kw for kw in keywords if kw in m_title]
        if len(matching_kws) > 0:
            logger.info(f"Polymarket zhoda: '{event_title}' -> '{m.title}' (Prob: {m.yes_probability*100}%)")
            return m.yes_probability
            
    return None

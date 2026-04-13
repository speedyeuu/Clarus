import httpx
from loguru import logger
import urllib.parse
from typing import Optional
from pydantic import BaseModel

class PolymarketMarket(BaseModel):
    title: str
    yes_probability: float

async def fetch_polymarket_economics() -> list[PolymarketMarket]:
    """
    Stahne aktivní trhy z Polymarketu, které se týkají makroekonomiky.
    Využívá veřejné Gamma API (nevyžaduje autentizaci).
    Vrací seznam relevantních trhů a jejich 'Yes' pravděpodobnosti (implikovaných cen).
    """
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "tag_id": 139, # Economics tag ID as a fallback if keyword empty, wait! Often better to filter manually
        "active": "true",
        "closed": "false",
        "limit": 100
    }
    
    # Query pro makroekonomiku:
    # Často je mnohem snazší použít /events, ale budeme iterovat markets a hledat klíčová slova
    keywords = ["fed", "cpi", "gdp", "jobless claims", "nfp", "payrolls", "ecb"]
    
    results = []
    logger.info("Fetching markets from Polymarket Gamma API...")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            markets_data = response.json()
            
            for m in markets_data:
                question = m.get("question", "").lower()
                
                # Zajímají nás pouze makro trhy z výše uvedených slov
                if any(kw in question for kw in keywords):
                    # Polymarket vrací pole 'outcomePrices'.
                    # Pro binární otázky (Yes/No) je na nultém indexu typicky "Yes"
                    outcomes = m.get("outcomes", [])
                    outcomePrices = m.get("outcomePrices", [])
                    
                    try:
                        yes_idx = outcomes.index("Yes")
                        yes_prob = float(outcomePrices[yes_idx])
                        
                        results.append(PolymarketMarket(
                            title=m.get("question", ""),
                            yes_probability=yes_prob
                        ))
                    except (ValueError, IndexError):
                        # Pokud trh nemá "Yes", přeskočíme
                        continue
                        
            return results
            
    except Exception as e:
        logger.error(f"Error fetching Polymarket data: {e}")
        return []

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

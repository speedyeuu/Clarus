import httpx
from pydantic import BaseModel
from loguru import logger
from typing import Optional
from config import get_settings

class SentimentData(BaseModel):
    long_pct: float
    short_pct: float

async def fetch_retail_sentiment() -> Optional[SentimentData]:
    """
    Získá komunitní náladu (Sentiment) od maloobchodních obchodníků přes volné API MyFXBook.
    Oandu jsme zahodili kvůli EU regulacím/placeným účtům.
    Vyžaduje v .env souboru MYFXBOOK_EMAIL a MYFXBOOK_PASSWORD.
    """
    settings = get_settings()
    
    # 1. Zkontrolujeme, zda vůbec má uživatel údaje
    if not hasattr(settings, 'myfxbook_email') or not settings.myfxbook_email:
        logger.warning("Chybí MYFXBOOK_EMAIL nebo MYFXBOOK_PASSWORD. Skóre retail sentimentu bude nulové.")
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Krok A: Přihlášení (Vytvoření jednorázové Session)
            login_url = f"https://www.myfxbook.com/api/login.json?email={settings.myfxbook_email}&password={settings.myfxbook_password}"
            r_login = await client.get(login_url)
            login_data = r_login.json()
            
            if login_data.get("error", False) == True:
                logger.error(f"MyFXBook odmítl přístup. Špatný login? Detail: {login_data.get('message')}")
                return None
                
            session_id = login_data.get("session")
            
            if not session_id:
                logger.error("MyFXBook nevrátil platné Session ID.")
                return None
                
            # Krok B: Stažení globální nálady na EURUSD
            url = f"https://www.myfxbook.com/api/get-community-outlook.json?session={session_id}"
            r_sentiment = await client.get(url)
            sentiment_data = r_sentiment.json()
            
            symbols = sentiment_data.get("symbols", [])
            for sym in symbols:
                if sym.get("name") == "EURUSD":
                    # Myfxbook vrací např. longPercentage = 65.4, takže převedeme na poměr 0-1
                    longs = float(sym.get("longPercentage", 50)) / 100.0
                    shorts = float(sym.get("shortPercentage", 50)) / 100.0
                    
                    logger.info(f"MyFXBook nahlásil Sentiment: Lidi z {longs*100}% kupují a ze {shorts*100}% prodávají.")
                    return SentimentData(long_pct=longs, short_pct=shorts)
                    
            logger.warning("V MyFXBook záznamech chyběl měnový pár EURUSD.")
            return None
            
    except Exception as e:
        logger.error(f"Chyba při komunikaci s MyFXBook: {e}")
        return None

from loguru import logger
from db.client import get_supabase
from pydantic import BaseModel

class NormalizationStats(BaseModel):
    indicator_name: str
    mean_surprise: float
    std_surprise: float

async def get_normalization_stats(indicator_name: str) -> NormalizationStats:
    """
    Získá statistiky potřebné pro normalizaci Z-Score z db.
    Pokud v db statistiky ještě nejsou dostatečné (nemáme historii), 
    použije hardcoded fallback "default_std", který dodává ze semínkových dat (schema.sql).
    """
    db = get_supabase()
    
    try:
        result = db.table("normalization_stats").select("*").eq("indicator_name", indicator_name).single().execute()
        data = result.data
        
        if data:
            # Pokud už máme dost dat (např. sample_count > 30), použili bychom reálné sd
            # Zatím ve fázi 1 použijeme default_std jako std_surprise, nebo real std_surprise
            mean_surp = data.get("mean_surprise", 0.0)
            
            # Priorita: reálná std (pokud existuje) -> default_std -> 1.0 (failsafe)
            real_std = data.get("std_surprise")
            default_std = data.get("default_std")
            
            # Rozumný odhad, reálné std má přednost jen pokud sample_count je dostatečný 
            # (tuto logiku pak rozvineme). Nyní vezmeme to, co je k dispozici.
            std_surp = real_std if real_std else (default_std if default_std else 1.0)
            
            return NormalizationStats(
                indicator_name=indicator_name,
                mean_surprise=mean_surp,
                std_surprise=std_surp
            )
            
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst normalizační data pro {indicator_name}: {e}")
        
    # Bezpečný failsafe
    return NormalizationStats(
        indicator_name=indicator_name,
        mean_surprise=0.0,
        std_surprise=1.0
    )


def normalize_surprise_to_score(actual: float, forecast: float, stats: NormalizationStats, invert: bool = False) -> float:
    """
    Vypočítá překvapení (surprise), z-score a přeloží to na škálu -3.0 až +3.0.
    
    :param actual: Skutečností vyhlášená data
    :param forecast: Tržní predikce
    :param stats: Historické mean/std
    :param invert: Zda vyšší číslo = horší pro měnu (typicky pro nezaměstnanost USD -> bearish USD -> bullish pro EUR)
                   Tedy invert=True pokud např. US nezaměstnanost překvapí vysoko (+).
    """
    # 1. Spočítat absolutní překvapení
    surprise = actual - forecast
    
    # 2. Z-Score (kolikrát je to větší než obvyklá odchylka)
    # std_surprise je vždy kladné
    z_score = (surprise - stats.mean_surprise) / stats.std_surprise
    
    # 3. Zohlednění polarity (USD vs EUR, "good vs bad" pro inflaci / labor)
    if invert:
        z_score = -z_score
        
    # 4. Samotný z-score (který typicky létá zhruba -3 až +3 sigma) mapujeme 1:1 na naši škálu 
    # V plan.md: "Tím dostaneš vždy číslo ve stejném měřítku... které zmapuješ PŘÍMO na škálu -3/+3"
    score = z_score
    
    # Clamp -3.0 až +3.0
    return max(-3.0, min(3.0, score))

def parse_forex_factory_value(value_str: str) -> float | None:
    """Pomocná funkce k převedení '0.3%' na 0.3"""
    if not value_str:
        return None
    try:
        # Odstranit procenta, K, M, B
        clean_str = value_str.upper().replace('%', '').strip()
        multiplier = 1.0
        if clean_str.endswith('K'):
            clean_str = clean_str[:-1]
            # NFP typicky vrací "215K", my můžeme držet jednotku v tisících pro obě (actual/forecast)
            # takže multiplier nepotřebujeme, pokud nechceme normalizovat absolutně. 
            # Pro zjednodušení to necháme v těch jednotkách, jaké to jsou
        elif clean_str.endswith('M'):
            clean_str = clean_str[:-1]
        elif clean_str.endswith('B'):
            clean_str = clean_str[:-1]
            
        return float(clean_str)
    except Exception:
        return None

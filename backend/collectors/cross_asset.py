import asyncio
import yfinance as yf
from loguru import logger
from typing import Optional

async def fetch_cross_asset_score(pair: str) -> Optional[float]:
    """
    Vypočítá Cross-Asset skóre (-10 až +10) založené na širším trhu.
    
    Korelace:
    1. S&P 500 (SPY): Akcie nahoru = Risk On = Dolar oslabuje (pro EURUSD bullish)
    2. Gold (GC=F): Zlato nahoru = Dolar oslabuje (pro EURUSD bullish)
    3. Oil (CL=F): Ropa nahoru = Inflační tlaky = Fed sazby nahoře = Dolar posiluje (pro EURUSD bearish)
    """
    tickers = {"SPY": "SPY", "Gold": "GC=F", "Oil": "CL=F"}
    
    def _blocking_fetch():
        data = yf.download(list(tickers.values()), period="30d", interval="1d")
        return data['Close'] if 'Close' in data else data['Adj Close']
        
    loop = asyncio.get_event_loop()
    try:
        df = await loop.run_in_executor(None, _blocking_fetch)
        
        if df.empty:
            return 0.0
            
        # Výpočet momentového Z-score (5denní vs 20denní průměr) pro každý asset
        scores = {}
        for name, ticker in tickers.items():
            if ticker not in df.columns:
                continue
            series = df[ticker].dropna()
            if len(series) < 20:
                continue
                
            sma5 = series.rolling(5).mean().iloc[-1]
            sma20 = series.rolling(20).mean().iloc[-1]
            std20 = series.rolling(20).std().iloc[-1]
            
            if std20 == 0:
                z_score = 0
            else:
                z_score = (sma5 - sma20) / std20
            scores[name] = z_score

        if not scores:
            return 0.0

        # Zohlednění pro základní (Base) a kótovací (Quote) měnu
        base = pair[:3]
        quote = pair[3:]
        
        # Sestavíme dopad na USD
        # SPY roste = USD oslabuje -> USD_impact je záporný
        spy_z = scores.get("SPY", 0.0)
        gold_z = scores.get("Gold", 0.0)
        oil_z = scores.get("Oil", 0.0)
        
        usd_strength = -spy_z - gold_z + oil_z  # Kladné = USD posiluje
        
        # Defaultní skóre páru (0.0 = neutrální)
        pair_score = 0.0
        
        if quote == "USD":
            # EUR/USD: USD roste = pár klesá (bearish)
            pair_score = -usd_strength
        elif base == "USD":
            # USD/JPY: USD roste = pár roste (bullish)
            pair_score = usd_strength
        else:
            # Křížové páry např. EUR/JPY, EUR/NZD. 
            # Cross assety jsou silně vázané na USD. Pro tyto páry použijeme zjednodušenou proxy:
            # Risk-on (SPY+) -> JPY oslabuje (safe haven klesá) -> EUR/JPY roste
            if quote == "JPY":
                pair_score = spy_z  # JPY je safe haven, takže při růstu SPY oslabí a pár roste
            elif base == "JPY":
                pair_score = -spy_z
            else:
                pair_score = spy_z * 0.5  # Risk-on mírně pomáhá rizikovějším měnám (NZD, AUD) vs EUR

        # Normalizujeme a ořízneme na škálu -10 až +10
        # Z-score běžně osciluje -2 až +2. Suma 3 assetů může být -6 až +6.
        final_score = float(max(-10.0, min(10.0, pair_score * 2.0)))
        
        logger.info(f"Cross-Asset Score pro {pair}: {final_score:.2f} (SPY={spy_z:.2f}, Gold={gold_z:.2f}, Oil={oil_z:.2f})")
        return final_score

    except Exception as e:
        logger.warning(f"Nelze stáhnout Cross-Asset data: {e}")
        return 0.0

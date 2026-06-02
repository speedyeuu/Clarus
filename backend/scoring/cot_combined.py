import scipy.stats

def score_cot_combined(
    base_net: float,       # Base Currency net noncommercial pozice
    quote_net: float,      # Quote Currency net noncommercial pozice
    base_lookback: list,   # 52 týdnů Base Currency dat
    quote_lookback: list,  # 52 týdnů Quote Currency dat
    pair: str = "EURUSD"
) -> float:
    """
    Kombinuje oba kontrakty do jednoho COT Bias skóre.

    Logika pro běžné páry (EURUSD, GBPUSD, EURNZD):
    - Base měna net long = Bullish pro pár
    - Quote měna net long = Bearish pro pár (inverze)

    Logika pro páry, kde je USD Base (USDJPY):
    - Base měna (USD - zde reprezentován jako DXY) net long = Bullish pro pár
    - Quote měna (JPY) net long = Bearish pro pár (inverze)
    """
    if not base_lookback or not quote_lookback:
        return 0.0
        
    # Percentily z historie 52 týdnů → raw hodnota -10.0 až +10.0
    base_pct = scipy.stats.percentileofscore(base_lookback, base_net)
    base_score = (base_pct / 100 * 20) - 10.0

    quote_pct = scipy.stats.percentileofscore(quote_lookback, quote_net)
    quote_score = (quote_pct / 100 * 20) - 10.0

    # Inverzní logika
    # V klasickém případě (Base vs Quote): 
    # High Base = Bullish (+), High Quote = Bearish (-)
    quote_score = -quote_score

    # Kombinace (60 % Base měna, 40 % Quote měna)
    combined = (base_score * 0.60) + (quote_score * 0.40)
    
    # Clamp na meze -10.0 až +10.0 bez zaokrouhlení
    return float(max(-10.0, min(10.0, combined)))

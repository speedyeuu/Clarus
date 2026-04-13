import scipy.stats

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
    if not eur_lookback or not dxy_lookback:
        return 0.0
        
    # EUR 6E: percentil v 52týdenním okně → -3.0 až +3.0
    eur_pct = scipy.stats.percentileofscore(eur_lookback, eur_net)
    eur_score = (eur_pct / 100 * 6) - 3.0

    # DXY DX: percentil → invertován (high DXY net long = bearish EUR)
    dxy_pct = scipy.stats.percentileofscore(dxy_lookback, dxy_net)
    # Normální percentil -3 až +3, pak přidáme mínus pro inverzi
    dxy_score = -((dxy_pct / 100 * 6) - 3.0)

    # Kombinace: EUR váha 60%, DXY váha 40%
    combined = (eur_score * 0.6) + (dxy_score * 0.4)
    
    # Clamp na meze bez zaokrouhlování na int!
    return max(-3.0, min(3.0, combined))


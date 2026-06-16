from loguru import logger
from datetime import datetime, timedelta
from typing import List, Dict
from db.client import get_supabase

# Budeme potřebovat kalendář z FF (už stažený a uložený do DB nebo stažený z netu)
# Polymarket probability a OIS signals

def calculate_confidence(events_count: int) -> float:
    """Čím více událostí se na daný den podílí, tím je VĚTŠÍ nejistota (větší možný rozptyl výsledků)."""
    if events_count == 0:
        return 0.85 # Jen drift, žádné zprávy = vysoká jistota
    elif events_count == 1:
        return 0.75
    elif events_count == 2:
        return 0.60
    return 0.30     # Mnoho zpráv = velká nejistota (může to dopadnout jakkoliv)


from scoring.mappings import SPECIFIC_TO_GENERIC

def map_probability_to_score_shift(probability: float, indicator_weight: float, invert: bool = False) -> float:
    """
    Z pravděpodobnosti Polymarket/Euribor vypočítá očekávaný posun skóre.

    Logika (Expected Value):
      shift = (prob × max_impact) - ((1 - prob) × max_impact)
      → při 50/50 je shift 0 (žádná predikce), při 100% je shift = max_impact.

    max_impact = weight × 10.0 (protože sub-indikátory jsou v rozsahu ±10)
    """
    # Max vliv indikátoru na celkové skóre = jeho váha × škála ±10
    max_impact = indicator_weight * 10.0

    # Expected Value: kladná pravděpodobnost = bullish shift, záporná = bearish
    shift = (probability * max_impact) - ((1.0 - probability) * max_impact)

    if invert:
        shift = -shift

    return shift


async def calculate_polymarket_calibration(pair: str = "EURUSD") -> float:
    """
    Porovnává historické předpovědi Polymarketu s reálnými výsledky z indicator_readings.
    Vrací koeficient spolehlivosti (dampening factor) od 0.1 do 1.0.
    """
    db = get_supabase()
    today_str = datetime.now().date().isoformat()
    
    try:
        # Načteme historické události, kde jsme měli Polymarket predikci
        res_events = db.table("upcoming_events")\
            .select("event_date, indicator_key, title, country, polymarket_yes_prob")\
            .lt("event_date", today_str)\
            .not_.is_("polymarket_yes_prob", "null")\
            .order("event_date", desc=True)\
            .limit(100)\
            .execute()
            
        events = res_events.data or []
        if not events:
            return 0.8  # Defaultní rozumné tlumení pokud nemáme historii
            
        # Načteme reálné zprávy pro porovnání
        res_readings = db.table("indicator_readings")\
            .select("date, indicator_name, surprise")\
            .lt("date", today_str)\
            .execute()
            
        readings = {(r["date"], r["indicator_name"]): r["surprise"] for r in (res_readings.data or [])}
        
        matches = []
        for ev in events:
            key = (ev["event_date"], ev["indicator_key"])
            if key in readings:
                surprise = readings[key]
                if surprise is not None:
                    matches.append((ev["polymarket_yes_prob"], surprise, ev["country"], ev["indicator_key"]))
                    
        if not matches:
            return 0.8
            
        correct = 0
        total = 0
        
        for prob, surprise, country, ind_key in matches:
            if surprise == 0:
                continue
                
            # Určíme, zda má vyšší pravděpodobnost znamenat kladné nebo záporné překvapení
            # (Inverze pro Base/Quote měnu)
            base_currency = pair[:3]
            quote_currency = pair[3:]
            
            invert = False
            if country == base_currency:
                invert = False
                if ind_key and "unemployment" in ind_key.lower():
                    invert = True
            elif country == quote_currency:
                invert = True
                if ind_key and "unemployment" in ind_key.lower():
                    invert = False
                    
            # Směr předpovídaný Polymarketem (očekáváme YES = růst hodnoty)
            pred_dir = 1 if prob > 0.5 else -1 if prob < 0.5 else 0
            if invert:
                pred_dir = -pred_dir
                
            actual_dir = 1 if surprise > 0 else -1
            
            if pred_dir != 0:
                total += 1
                if pred_dir == actual_dir:
                    correct += 1
                    
        if total < 5:
            return 0.8  # Příliš málo vzorků pro statistiku
            
        accuracy = correct / total
        # Koeficient spolehlivosti: pokud je úspěšnost 50% (náhoda), factor je 0.0.
        # Pokud je úspěšnost 100% nebo 0% (konzistentně naopak), factor je 1.0.
        calibration_factor = 2.0 * abs(accuracy - 0.5)
        
        logger.info(f"[Polymarket Calibration] Historická úspěšnost Polymarketu: {correct}/{total} ({accuracy*100:.1f}%). Calibration factor: {calibration_factor:.2f}")
        return max(0.1, min(1.0, calibration_factor))
        
    except Exception as e:
        logger.warning(f"Chyba při výpočtu kalibrace Polymarketu: {e}")
        return 0.8

async def generate_7day_prediction(current_total_score: float, current_weights: Dict[str, float], pair: str = "EURUSD"):
    """
    Vygeneruje odhad skóre na dalších 7 dní a zapíše do tabulky predictions.

    Vylepšení:
      1. Confidence bands: více eventů = VĚTŠÍ nejistota (každý může překvapit)
      2. Mean reversion se zastaví den před high-impact eventem (NFP, CPI, FOMC)
      3. Scénářová analýza: beat vs miss trajektorie
      4. Lidsky čitelný výstup uložený v metadatech
    """
    db = get_supabase()
    today_date = datetime.now().date()
    today_str = today_date.isoformat()

    logger.info("Generování 7denní predikce (s vylepšenou logikou)...")

    # 1. Kalibrační faktor pro Polymarket
    calibration_factor = await calculate_polymarket_calibration(pair)

    base_curr = pair[:3]
    quote_curr = pair[3:]
    cutoff = (today_date + timedelta(days=7)).isoformat()
    try:
        res = (
            db.table("upcoming_events")
            .select("*")
            .gt("event_date", today_str)
            .lte("event_date", cutoff)
            .in_("country", [base_curr, quote_curr])
            .execute()
        )
        upcoming = res.data or []
    except Exception as e:
        logger.warning(f"Nelze přečíst nadcházející události: {e}")
        upcoming = []

    # Seskupit podle data
    events_by_date: Dict[str, List] = {}
    for ev in upcoming:
        date_key = ev["event_date"]
        events_by_date.setdefault(date_key, []).append(ev)

    # HIGH-IMPACT eventy pro zastavení mean reversion
    HIGH_IMPACT_KEYS = {
        "nfp_us", "cpi_us", "cpi_eu", "cpi_uk", "pce_us",
        "fed_rate", "ecb_rate", "boe_rate", "gdp_flash_us", "gdp_flash_eu", "gdp_flash_uk"
    }

    def is_high_impact_day(date_str: str) -> bool:
        """Zjistí jestli daný den má high-impact event."""
        evs = events_by_date.get(date_str, [])
        return any(
            ev.get("indicator_key") in HIGH_IMPACT_KEYS or
            str(ev.get("impact", "")).lower() in ("high", "red")
            for ev in evs
        )

    # Mean reversion: 0.12 bodu/den (pomalejší než dřív = realističtější)
    mean_reversion_daily = 0.12

    # Helper: vypočítá shift pro jeden event při dané pravděpodobnosti
    def calc_event_shift(ev: dict, prob_override: float | None = None) -> float:
        indicator_key = ev.get("indicator_key")
        country = ev.get("country")
        generic_key = SPECIFIC_TO_GENERIC.get(indicator_key, indicator_key) if indicator_key else None
        weight = current_weights.get(generic_key, 0.0) if generic_key else 0.0

        if prob_override is not None:
            prob = prob_override
        elif ev.get("polymarket_yes_prob") is not None:
            raw_prob = ev["polymarket_yes_prob"]
            prob = 0.5 + (raw_prob - 0.5) * calibration_factor
        elif ev.get("euribor_signal") is not None:
            prob = float(ev["euribor_signal"])
        else:
            prob = 0.5

        base_currency = pair[:3]
        quote_currency = pair[3:]
        
        invert = False
        if country == base_currency:
            invert = False
            if indicator_key and "unemployment" in indicator_key.lower():
                invert = True
        elif country == quote_currency:
            invert = True
            if indicator_key and "unemployment" in indicator_key.lower():
                invert = False

        return map_probability_to_score_shift(prob, weight, invert)

    # Tři trajektorie: baseline, beat scénář, miss scénář
    running_baseline = current_total_score
    running_beat = current_total_score
    running_miss = current_total_score

    predictions_to_save = []
    week_catalysts = []  # Pro lidsky čitelný výstup

    for i in range(1, 8):
        pred_date = today_date + timedelta(days=i)
        pred_str = pred_date.isoformat()
        next_day_str = (pred_date + timedelta(days=1)).isoformat()

        day_events = events_by_date.get(pred_str, [])

        # --- Mean reversion ---
        # Zastavíme ji pokud dnes nebo zítra je high-impact event
        day_has_high_impact = is_high_impact_day(pred_str)
        next_has_high_impact = is_high_impact_day(next_day_str)
        apply_mean_reversion = not (day_has_high_impact or next_has_high_impact)

        if apply_mean_reversion:
            for score_ref in ["baseline", "beat", "miss"]:
                s = locals()[f"running_{score_ref}"]
                if s > 0:
                    if score_ref == "baseline":
                        running_baseline -= min(running_baseline, mean_reversion_daily)
                    elif score_ref == "beat":
                        running_beat -= min(running_beat, mean_reversion_daily)
                    else:
                        running_miss -= min(running_miss, mean_reversion_daily)
                elif s < 0:
                    if score_ref == "baseline":
                        running_baseline += min(abs(running_baseline), mean_reversion_daily)
                    elif score_ref == "beat":
                        running_beat += min(abs(running_beat), mean_reversion_daily)
                    else:
                        running_miss += min(abs(running_miss), mean_reversion_daily)
        else:
            logger.debug(f"  [{pred_str}] Mean reversion pozastavena (high-impact event blízko)")

        # --- Výpočet posunů pro každý den ---
        baseline_shift = 0.0
        beat_shift = 0.0
        miss_shift = 0.0

        for ev in day_events:
            baseline_shift += calc_event_shift(ev)           # Reálná pravděpodobnost
            beat_shift += calc_event_shift(ev, prob_override=0.85)   # Beat scénář
            miss_shift += calc_event_shift(ev, prob_override=0.15)   # Miss scénář

            indicator_key = ev.get("indicator_key")
            generic_key = SPECIFIC_TO_GENERIC.get(indicator_key, indicator_key) if indicator_key else None
            weight = current_weights.get(generic_key, 0.0) if generic_key else 0.0
            logger.debug(
                f"  Event [{ev.get('title')}] key={indicator_key}→{generic_key} "
                f"weight={weight:.3f} baseline_shift={calc_event_shift(ev):.4f}"
            )

            # Zaznamenat katalyzátor pro týdenní přehled
            if weight > 0.05 and i <= 7:
                week_catalysts.append({
                    "day": pred_str,
                    "title": ev.get("title", ""),
                    "weight": weight,
                    "expected_shift": calc_event_shift(ev),
                    "beat_shift": calc_event_shift(ev, 0.85),
                    "miss_shift": calc_event_shift(ev, 0.15),
                })

        running_baseline = max(-10.0, min(10.0, running_baseline + baseline_shift))
        running_beat     = max(-10.0, min(10.0, running_beat + beat_shift))
        running_miss     = max(-10.0, min(10.0, running_miss + miss_shift))

        # --- Confidence bands ---
        base_band = 0.8                          # Základní nejistota bez zpráv
        event_uncertainty = len(day_events) * 0.5  # +0.5 za každý event
        band_width = float(min(4.0, base_band + event_uncertainty))

        # Informace pro confidence — více událostí = VĚTŠÍ nejistota = NIŽŠÍ confidence
        n_ev = len(day_events)
        confidence = calculate_confidence(n_ev)

        record = {
            "created_date": today_str,
            "prediction_date": pred_str,
            "pair": pair,
            "predicted_score_mid":  float(running_baseline),
            "predicted_score_low":  float(max(-10.0, min(10.0, running_baseline - band_width))),
            "predicted_score_high": float(max(-10.0, min(10.0, running_baseline + band_width))),
            "confidence": confidence,
            "upcoming_events": [ev["title"] for ev in day_events],
            # Scénářová analýza
            "scenario_beat": float(running_beat),
            "scenario_miss": float(running_miss),
            # Mean reversion info
            "mean_reversion_applied": apply_mean_reversion,
        }
        predictions_to_save.append(record)

    # --- Lidsky čitelný týdenní přehled ---
    end_score = predictions_to_save[-1]["predicted_score_mid"] if predictions_to_save else current_total_score
    score_change = end_score - current_total_score

    if end_score > 3.0:
        direction_label = f"📈 Bullish {pair}"
    elif end_score > 1.0:
        direction_label = f"🟢 Mírně Bullish {pair}"
    elif end_score > -1.0:
        direction_label = f"⚪ Neutrální {pair}"
    elif end_score > -3.0:
        direction_label = f"🟡 Mírně Bearish {pair}"
    else:
        direction_label = f"📉 Bearish {pair}"

    change_str = f"{score_change:+.2f} bodu" if abs(score_change) > 0.1 else "bez velké změny"

    # Nejdůležitější katalyzátor týdne (nejvyšší váha)
    if week_catalysts:
        top_catalyst = max(week_catalysts, key=lambda x: x["weight"])
        catalyst_info = (
            f"{top_catalyst['title']} ({top_catalyst['day']}) — "
            f"beat: {top_catalyst['beat_shift']:+.2f}, miss: {top_catalyst['miss_shift']:+.2f}"
        )
    else:
        catalyst_info = "Žádné klíčové zprávy tento týden"

    week_summary = {
        "direction_label": direction_label,
        "score_start": round(current_total_score, 2),
        "score_end_expected": round(end_score, 2),
        "score_change": round(score_change, 2),
        "change_description": change_str,
        "key_catalyst": catalyst_info,
        "all_catalysts": week_catalysts,
    }

    logger.info(
        f"Predikce dokončena: {direction_label} | "
        f"Score {current_total_score:.2f} → {end_score:.2f} ({change_str}) | "
        f"Klíčový katalyzátor: {catalyst_info}"
    )

    # Uložit predikce do DB
    try:
        # Smazat staré predikce pro daný pár od dneška dál, abychom nenakumulovali duplikáty
        db.table("predictions").delete().gte("prediction_date", today_str).eq("pair", pair).execute()
        
        # Uložit nové
        if predictions_to_save:
            db.table("predictions").insert(predictions_to_save).execute()
            logger.info("Úspěšně uloženy predikce na 7 dní.")
            
    except Exception as e:
        logger.error(f"Nepodařilo se uložit predikce do DB: {e}")

    return week_summary

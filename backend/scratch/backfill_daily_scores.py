import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_supabase
from loguru import logger
from scoring.engine import calculate_total_score
from scoring.indicators import score_combined_interest_rates
from collectors.bond_yields import fetch_2y_yield_histories
from scheduler.daily_update import fetch_previous_scores, CARRY_FORWARD_CONFIG

DEFAULT_RATES = {
    "fed_rate": 5.25, "ecb_rate": 4.25, "boe_rate": 5.25,
    "boj_rate": 0.25, "rbnz_rate": 5.50, "rba_rate": 4.35,
    "boc_rate": 5.00, "xau_rate": 0.00
}
COUNTRY_TO_RATE_KEY = {
    "USD": "fed_rate", "EUR": "ecb_rate", "GBP": "boe_rate",
    "JPY": "boj_rate", "NZD": "rbnz_rate", "AUD": "rba_rate",
    "CAD": "boc_rate", "XAU": "xau_rate",
}

async def backfill_pair(pair: str, days: int = 30):
    db = get_supabase()
    today = date.today()
    logger.info(f"== Spouštím backfill pro {pair} ({days} dní) ==")
    
    # Stáhneme bond yields na 120 dní (abychom měli dost dat pro 90d lookback pro jakýkoli den v posledních 30 dnech)
    bond_hists = await fetch_2y_yield_histories(lookback_days=120, pair=pair)
    
    base_cur = pair[:3]
    quote_cur = pair[3:]
    base_rate_key = COUNTRY_TO_RATE_KEY.get(base_cur)
    quote_rate_key = COUNTRY_TO_RATE_KEY.get(quote_cur)

    for d in range(days, -1, -1):
        sim_date = today - timedelta(days=d)
        sim_date_str = sim_date.isoformat()
        
        old_res = db.table("daily_scores").select("*").eq("pair", pair).eq("date", sim_date_str).execute()
        if not old_res.data:
            continue # Pokud chybí záznam, nebudeme ho celý rekonstruovat
        
        old_row = old_res.data[0]
        
        # 1. Zjistit bond history k danému datu
        q_hist, b_hist = None, None
        if bond_hists:
            full_q, full_b = bond_hists
            q_hist = {k: v for k, v in full_q.items() if k <= sim_date_str}
            b_hist = {k: v for k, v in full_b.items() if k <= sim_date_str}
            q_keys = sorted(q_hist.keys())[-90:]
            b_keys = sorted(b_hist.keys())[-90:]
            q_hist = {k: q_hist[k] for k in q_keys}
            b_hist = {k: b_hist[k] for k in b_keys}
            
        # 2. Zjistit policy rates k danému datu
        res_quote = db.table("indicator_readings").select("actual").eq("indicator_name", quote_rate_key).eq("pair", pair).lte("date", sim_date_str).order("date", desc=True).limit(1).execute()
        res_base = db.table("indicator_readings").select("actual").eq("indicator_name", base_rate_key).eq("pair", pair).lte("date", sim_date_str).order("date", desc=True).limit(1).execute()
        
        latest_quote = float(res_quote.data[0]["actual"]) if res_quote.data else DEFAULT_RATES.get(quote_rate_key, 5.0)
        latest_base = float(res_base.data[0]["actual"]) if res_base.data else DEFAULT_RATES.get(base_rate_key, 5.0)

        # 3. Spočítat nový úrokový signál
        new_ir_score = 0.0
        if q_hist and b_hist:
            combined_ir, _, _, _ = score_combined_interest_rates(q_hist, b_hist, latest_quote, latest_base, pair)
            new_ir_score = combined_ir
        else:
            rate_diff = latest_base - latest_quote
            new_ir_score = float(max(-10.0, min(10.0, rate_diff * 2.0)))
            
        # 4. Makro indikátory (bez rozpadu)
        macro_categories = ["inflation", "gdp", "labor", "spmi", "mpmi", "retail_sales"]
        macro_scores = {}
        macro_ages = {}
        for gen_ind in macro_categories:
            config = CARRY_FORWARD_CONFIG[gen_ind]
            max_days = config["max_days"]
            spec_keys = [k for k, v in fetch_previous_scores.__globals__.get("SPECIFIC_TO_GENERIC", {}).items() if v == gen_ind]
            if not spec_keys:
                # Ošklivý hack, protože SPECIFIC_TO_GENERIC tam normálně je
                if gen_ind == "inflation": spec_keys = ["cpi_us", "cpi_eu", "cpi_uk", "cpi_jp", "cpi_nz", "cpi_au", "cpi_ca"]
                elif gen_ind == "labor": spec_keys = ["nfp_us", "unemployment_eu", "unemployment_uk", "unemployment_jp", "unemployment_nz", "unemployment_au", "unemployment_ca"]
                elif gen_ind == "gdp": spec_keys = ["gdp_us", "gdp_eu", "gdp_uk", "gdp_jp", "gdp_nz", "gdp_au", "gdp_ca"]
                elif gen_ind == "spmi": spec_keys = ["spmi_us", "spmi_eu", "spmi_uk", "spmi_jp", "spmi_nz", "spmi_au", "spmi_ca"]
                elif gen_ind == "mpmi": spec_keys = ["mpmi_us", "mpmi_eu", "mpmi_uk", "mpmi_jp", "mpmi_nz", "mpmi_au", "mpmi_ca"]
                elif gen_ind == "retail_sales": spec_keys = ["retail_us", "retail_eu", "retail_uk", "retail_jp", "retail_nz", "retail_au", "retail_ca"]
            
            cutoff = (sim_date - timedelta(days=max_days)).isoformat()
            res = db.table("indicator_readings").select("date, raw_score").eq("pair", pair).in_("indicator_name", spec_keys).gte("date", cutoff).lte("date", sim_date_str).order("date", desc=True).execute()
            if res.data:
                latest_date_str = res.data[0]["date"]
                latest_date = date.fromisoformat(latest_date_str)
                age_days = (sim_date - latest_date).days
                scores_on_latest = [r["raw_score"] for r in res.data if r["date"] == latest_date_str]
                if scores_on_latest:
                    macro_scores[gen_ind] = sum(scores_on_latest) / len(scores_on_latest)
                    macro_ages[gen_ind] = age_days
            else:
                macro_scores[gen_ind] = 0.0
                macro_ages[gen_ind] = 30
        
        # 5. Složit všechny subs-scores
        scores = {
            "interest_rates": new_ir_score,
            "cot": old_row.get("score_cot") or 0.0,
            "seasonality": old_row.get("score_seasonality") or 0.0,
            "retail_sentiment": old_row.get("score_retail_sentiment") or 0.0,
            "trend": old_row.get("score_trend") or 0.0,
        }
        scores.update({k: v for k, v in macro_scores.items() if v is not None})
        
        # 6. Odhadnout věk
        ages = {
            "interest_rates": 0, "cot": 0, "seasonality": 0, "retail_sentiment": 0, "trend": 0,
        }
        ages.update(macro_ages)
        
        # 7. Spustit Engine s novými interest_rates a ne-decayed makro
        score_model = await calculate_total_score(scores, ages)
        new_total = score_model.total
        
        logger.info(f"{sim_date_str} [{pair}]: old Total={old_row.get('total_score')} -> new Total={new_total:.3f}")
        
        # 8. Zapsat zpět do DB včetně makro score!
        db.table("daily_scores").update({
            "score_interest_rates": new_ir_score,
            "total_score": new_total,
            "score_inflation": macro_scores.get("inflation"),
            "score_labor": macro_scores.get("labor"),
            "score_gdp": macro_scores.get("gdp"),
            "score_spmi": macro_scores.get("spmi"),
            "score_mpmi": macro_scores.get("mpmi"),
            "score_retail_sales": macro_scores.get("retail_sales"),
        }).eq("id", old_row["id"]).execute()

async def main():
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "EURJPY", "EURNZD", "XAUUSD"]
    for pair in pairs:
        await backfill_pair(pair, 30)
    logger.info("Hotovo!")

if __name__ == "__main__":
    asyncio.run(main())

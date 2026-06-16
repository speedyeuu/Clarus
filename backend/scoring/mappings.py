"""
Shared mapping: specific indicator keys → generic engine keys.

Used by both daily_update.py (to aggregate FF events into engine categories)
and prediction/generator.py (to calculate expected shifts from upcoming events).
"""

# Mapování specifických klíčů z upcoming_events / indicator_readings → generické klíče vah modelu.
# Např. "cpi_us" → "inflation", "nfp_eu" → "labor" atd.
SPECIFIC_TO_GENERIC = {
    # ── INFLATION ──
    "cpi_us":           "inflation",
    "cpi_eu":           "inflation",
    "cpi_uk":           "inflation",
    "cpi_jpy":          "inflation",
    "cpi_nzd":          "inflation",
    "pce_us":           "inflation",
    "pce_eu":           "inflation",
    "pce_uk":           "inflation",
    "pce_jpy":          "inflation",
    "pce_nzd":          "inflation",

    # ── LABOR ──
    "nfp_us":           "labor",
    "nfp_eu":           "labor",
    "nfp_uk":           "labor",
    "nfp_jpy":          "labor",
    "nfp_nzd":          "labor",
    "unemployment_us":  "labor",
    "unemployment_eu":  "labor",
    "unemployment_uk":  "labor",
    "unemployment_jpy": "labor",
    "unemployment_nzd": "labor",

    # ── GDP ──
    "gdp_flash_us":     "gdp",
    "gdp_flash_eu":     "gdp",
    "gdp_flash_uk":     "gdp",
    "gdp_flash_jpy":    "gdp",
    "gdp_flash_nzd":    "gdp",

    # ── MANUFACTURING PMI ──
    "mpmi_us":          "mpmi",
    "mpmi_eu":          "mpmi",
    "mpmi_uk":          "mpmi",
    "mpmi_jpy":         "mpmi",
    "mpmi_nzd":         "mpmi",

    # ── SERVICES PMI ──
    "spmi_us":          "spmi",
    "spmi_eu":          "spmi",
    "spmi_uk":          "spmi",
    "spmi_jpy":         "spmi",
    "spmi_nzd":         "spmi",

    # ── RETAIL SALES ──
    "retail_sales_us":  "retail_sales",
    "retail_sales_eu":  "retail_sales",
    "retail_sales_uk":  "retail_sales",
    "retail_sales_jpy": "retail_sales",
    "retail_sales_nzd": "retail_sales",
    "retail_sales_jp":  "retail_sales",

    # ── INTEREST RATES (rate decisions) ──
    "fed_rate":         "interest_rates",
    "ecb_rate":         "interest_rates",
    "boe_rate":         "interest_rates",
    "boc_rate":         "interest_rates",
    "boj_rate":         "interest_rates",
    "rbnz_rate":        "interest_rates",
}

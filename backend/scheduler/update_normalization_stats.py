"""
update_normalization_stats.py
------------------------------
Přepočítá mean_surprise a std_surprise pro každý indikátor
na základě reálných dat z tabulky indicator_readings.

Logika:
  - Pokud je vzorků >= MIN_SAMPLES: přepíše std_surprise reálnou hodnotou
  - Pokud je vzorků < MIN_SAMPLES:  aktualizuje jen sample_count, zachová default_std

Spouští se automaticky na konci každého run_daily_update() pipeline.
Může se spustit i ručně: python backend/scheduler/update_normalization_stats.py
"""
import statistics
from collections import defaultdict
from loguru import logger
import sys
import os
import asyncio

# Umožní spuštění samostatně z terminálu
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_supabase

# Minimální počet vzorků, aby se přepsala default_std reálnou hodnotou
MIN_SAMPLES = 10


async def update_normalization_stats(pair: str = "EURUSD"):
    """
    Přepočítá normalizační statistiky (mean_surprise, std_surprise, sample_count)
    pro každý indikátor na základě reálných surprise hodnot v indicator_readings.

    Surprise = actual - forecast (uloženo jako float sloupec v DB).
    Pokud je vzorků méně než MIN_SAMPLES, zachováme konzervativní default_std
    z původního schema.sql seedu a jen aktualizujeme sample_count.
    """
    db = get_supabase()

    logger.info("── Aktualizuji normalizační statistiky z reálných dat ──")

    try:
        result = (
            db.table("indicator_readings")
            .select("indicator_name, surprise")
            .eq("pair", pair)
            .not_.is_("surprise", "null")
            .execute()
        )
    except Exception as e:
        logger.error(f"Chyba při čtení indicator_readings pro normalizaci: {e}")
        return

    if not result.data:
        logger.info(
            "Žádná surprise data v indicator_readings — "
            "normalizační statistiky zůstanou beze změny."
        )
        return

    # Seskupení surprise hodnot podle indikátoru
    groups: dict[str, list[float]] = defaultdict(list)
    for row in result.data:
        name = row.get("indicator_name")
        surprise = row.get("surprise")
        if name and surprise is not None:
            groups[name].append(float(surprise))

    updated_count = 0
    kept_default_count = 0

    for indicator_name, surprises in groups.items():
        n = len(surprises)

        if n < MIN_SAMPLES:
            # Nedostatek dat → jen aktualizujeme počet (std zůstane default)
            try:
                db.table("normalization_stats").update({
                    "sample_count": n,
                }).eq("indicator_name", indicator_name).execute()
                logger.debug(
                    f"[{indicator_name}]: {n} vzorků < {MIN_SAMPLES} "
                    f"→ zachovávám default_std (sample_count={n})"
                )
                kept_default_count += 1
            except Exception as e:
                logger.warning(
                    f"Nelze aktualizovat sample_count pro {indicator_name}: {e}"
                )
            continue

        # Máme dost dat — vypočítáme reálné statistiky
        mean_s = round(statistics.mean(surprises), 6)
        std_s = round(statistics.stdev(surprises), 6) if n > 1 else 1.0

        # Záchrana před nulovou nebo zanedbatelnou směrodatnou odchylkou
        if std_s < 0.0001:
            std_s = 0.0001

        try:
            db.table("normalization_stats").upsert({
                "indicator_name": indicator_name,
                "mean_surprise": mean_s,
                "std_surprise": std_s,
                "sample_count": n,
            }).execute()
            logger.info(
                f"[{indicator_name}]: mean={mean_s:.4f}, std={std_s:.4f} "
                f"(n={n}) ✓"
            )
            updated_count += 1
        except Exception as e:
            logger.warning(
                f"Chyba při upsert normalization_stats pro {indicator_name}: {e}"
            )

    logger.info(
        f"Normalizační statistiky: {updated_count} přepočítáno, "
        f"{kept_default_count} zachováno (nedostatek dat)."
    )


if __name__ == "__main__":
    asyncio.run(update_normalization_stats())

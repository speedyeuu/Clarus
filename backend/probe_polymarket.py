import httpx

r = httpx.get("https://gamma-api.polymarket.com/markets", params={"active": "true", "closed": "false", "limit": 200}, timeout=15)
data = r.json()
print(f"Celkem trhu: {len(data)}")

keywords = ["fed", "cpi", "gdp", "nfp", "payroll", "ecb", "inflation", "rate cut", "jobless", "pmi", "lagarde", "powell", "euribor", "tariff", "recession", "euro", "eur"]
found = [m for m in data if any(kw in m.get("question", "").lower() for kw in keywords)]
print(f"Nalezeno makro trhu: {len(found)}")
for m in found[:30]:
    outcomes = m.get("outcomes", [])
    prices = m.get("outcomePrices", [])
    try:
        yi = outcomes.index("Yes")
        prob = float(prices[yi])
        print(f"  [{prob*100:.0f}%] {m['question']}")
    except Exception:
        pass

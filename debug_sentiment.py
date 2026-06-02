import asyncio
from dotenv import load_dotenv

load_dotenv()

from backend.collectors.sentiment import fetch_retail_sentiment
from backend.collectors.cot import fetch_cot_data

async def main():
    print("Fetching USDJPY Retail Sentiment...")
    sent = await fetch_retail_sentiment("USDJPY")
    if sent:
        print(f"Retail: LONG {sent.long_pct*100:.1f}%, SHORT {sent.short_pct*100:.1f}%")
        
    print("\nFetching USDJPY COT Data...")
    cot = await fetch_cot_data("USDJPY")
    if cot:
        print(f"COT JPY Net Pos: {cot.base_net_position}")
        print(f"COT DXY Net Pos: {cot.dxy_net_position}")
        print(f"COT JPY 52W Min/Max: {min(cot.base_history_52w)} / {max(cot.base_history_52w)}")
        print(f"COT DXY 52W Min/Max: {min(cot.dxy_history_52w)} / {max(cot.dxy_history_52w)}")

if __name__ == "__main__":
    asyncio.run(main())

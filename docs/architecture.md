# Architektura Clarus

Clarus je aplikace pro fundamentální scoring měnových párů. Na základě makroekonomických dat a tržního sentimentu predikuje, zda má daný měnový pár (např. EUR/USD) tendenci růst nebo klesat.

## Systémové komponenty

1. **Sběrače dat (Collectors)**:
   - Sledují makroekonomická vyhlašování (Forex Factory)
   - Sledují chování obchodníků (COT reporty)
   - Sledují maloobchodní sentiment (MyFXBook)
   - Sledují úrokové sazby a dluhopisy (FRED, ECB)

2. **Scoring Engine**:
   - Přebírá nasbíraná data a počítá skóre pro 11 indikátorů.
   - Vypočítává celkové vážené skóre (-10 až +10).

3. **Predikce (Prediction Generator)**:
   - Předpovídá budoucí vývoj skóre v následujících 7 dnech pomocí budoucích událostí (Polymarket, OIS úrokové signály).

4. **Frontend**:
   - Zobrazuje zpracovaná data pomocí Next.js Dashboardu.

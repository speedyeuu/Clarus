# Clarus – EUR/USD Fundamental Swing Trading Assistant

Aplikace pro analýzu a predikci fundamentálního vývoje měnového páru EUR/USD na celočíselné stupnici [-10, 10].

## 📂 Struktura projektu

*   **`frontend/`** – Webové uživatelské rozhraní postavené na Next.js 16 (React 19) a Tailwind CSS.
*   **`backend/`** – Python FastAPI server provádějící scoring, normalizaci (z-score) a predikce.
*   **`database/`** – SQL schémata a databázové testovací/kalibrační skripty.
*   **`docs/`** – Kompletní dokumentace, specifikace scoring vzorců a plánů.

## 🚀 Jak spustit projekt

### 1. Inicializace reálných dat (Historický Backfill)
Pro stažení reálné historie cen, COT pozic a FRED makroekonomických vyhlášení za posledních 30 dní spusťte:
```bash
cd backend
python3 seed_real_history.py
```

### 2. Spuštění Backend API (Python)
Spustí lokální server pro zpracování požadavků na adrese `http://localhost:8000`:
```bash
cd backend
python3 -m uvicorn main:app --reload --port 8000
```

### 3. Spuštění Webu (Next.js)
Spustí vývojářský server na adrese `http://localhost:3000`:
```bash
cd frontend
npm run dev
```

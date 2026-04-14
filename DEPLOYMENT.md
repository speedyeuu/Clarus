# 🚀 Deployment Guide — Fundament Analyzér (Clarus)

> Tento dokument popisuje jak nasadit aplikaci do produkce pro tisíce uživatelů.
> Backend → Railway | Frontend → Vercel | Cron → cron-job.org

---

## Architektura

```
cron-job.org (jednou denně v 19:00 UTC)
        │
        │  POST /api/cron/update
        │  Header: Authorization: Bearer <CRON_SECRET>
        ▼
┌─────────────────────┐
│  Backend (FastAPI)  │  ← Railway.app
│  backend/           │  ← spustí pipeline 1× denně
└────────┬────────────┘
         │  uloží výsledek
         ▼
┌─────────────────────┐
│     Supabase        │  ← centrální cloudová databáze
│  (již nastaveno)    │
└────────┬────────────┘
         │  čtou data přes API
         ▼
┌─────────────────────┐
│  Frontend (Next.js) │  ← Vercel
│  frontend/          │  ← tisíce uživatelů, CDN
└─────────────────────┘
```

---

## KROK 1 — Deploy backendu na Railway (~10 minut)

1. Jdi na **https://railway.app** → přihlas se přes GitHub
2. Klikni **New Project → Deploy from GitHub repo**
3. Vyber repozitář: `speedyeuu/Clarus`
4. Nastav **Root Directory**: `backend`
5. Railway automaticky detekuje Python — zkontroluj že používá `requirements.txt`
6. Přidej **Environment Variables** (Settings → Variables):

```env
SUPABASE_URL=<stejná hodnota jako v .env>
SUPABASE_SERVICE_KEY=<stejná hodnota jako v .env>
CRON_SECRET=<stejná hodnota jako v .env>
GEMINI_API_KEY=<stejná hodnota jako v .env>
EODHD_API_KEY=<stejná hodnota jako v .env>
```

7. Klikni **Deploy** → po ~2 minutách dostaneš URL:
   ```
   https://clarus-backend.railway.app
   ```

8. Otestuj: `GET https://clarus-backend.railway.app/health` → mělo by vrátit `{"status": "ok"}`

---

## KROK 2 — Deploy frontendu na Vercel (~5 minut)

1. Jdi na **https://vercel.com** → přihlas se přes GitHub
2. Klikni **New Project → Import** → vyber `speedyeuu/Clarus`
3. Nastav **Root Directory**: `frontend`
4. Framework: **Next.js** (detekováno automaticky)
5. Přidej **Environment Variables**:

```env
NEXT_PUBLIC_API_URL=https://clarus-backend.railway.app
```

6. Klikni **Deploy** → dostaneš URL:
   ```
   https://clarus.vercel.app
   ```
   (nebo vlastní doménu pokud máš)

7. Každý push na `main` větev na GitHubu → automatický re-deploy frontendu ✅

---

## KROK 3 — Automatický denní update přes cron-job.org (~3 minuty)

1. Jdi na **https://cron-job.org** → registrace zdarma (email)
2. Klikni **Create cronjob** a vyplň:

| Pole | Hodnota |
|------|---------|
| URL | `https://clarus-backend.railway.app/api/cron/update` |
| Method | `POST` |
| Header name | `Authorization` |
| Header value | `Bearer <tvůj CRON_SECRET z .env>` |
| Schedule | Každý den v **19:00 UTC** |

3. Uložit → aktivovat

> ⚠️ **Důležité:** CRON_SECRET musí být stejný jako v Railway Environment Variables!

---

## Výsledný flow po nasazení

```
19:00 UTC každý pracovní den:

1. cron-job.org pošle POST na Railway backend
2. Backend ověří CRON_SECRET token
3. Spustí run_daily_update():
   - Stáhne COT data (CFTC.gov)
   - Stáhne Forex Factory kalendář
   - Načte carry-forward hodnoty z Supabase
   - Vypočítá skóre pro všechny indikátory
   - Uloží daily_scores do Supabase
   - Přepočítá normalizační statistiky
   - Vygeneruje 7denní predikci
4. Všichni uživatelé na Vercelu vidí aktuální data (čtou ze Supabase)
```

---

## Poznámky

- **Supabase** je již nastaven a funguje — není třeba nic měnit
- **Windows `run_daily.bat`** je jen pro lokální testování, na produkci se nepoužívá
- **Vercel** poskytuje CDN → rychlé načítání pro uživatele po celém světě
- **Railway** free tier má 500 hodin/měsíc — pro produkci doporučuji Hobby plán ($5/měsíc)

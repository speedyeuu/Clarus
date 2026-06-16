FROM python:3.11-slim

# Instalace systémových závislostí (pokud jsou potřeba)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Nejprve zkopírujeme requirements.txt pro efektivní využití Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Zkopírujeme zbytek zdrojových kódů backendu
COPY . .

# Otevřeme port 8000
EXPOSE 8000

# Spustíme Uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

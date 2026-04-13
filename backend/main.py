from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
from api import scores, predictions, events, autoresearch, cron


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Server started. (Scheduler odpojen - spoléhá se na externí systémoý CRON)")
    yield
    # Shutdown
    logger.info("Server stopped")


app = FastAPI(
    title="EUR/USD Fundamental Analyzer API",
    description="Backend pro fundamentální scoring EUR/USD páru",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://your-vercel-domain.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routery
app.include_router(scores.router, prefix="/api/score", tags=["Scores"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Predictions"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(autoresearch.router, prefix="/api/autoresearch", tags=["Autoresearch"])
app.include_router(cron.router, prefix="/api/cron", tags=["Cron"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

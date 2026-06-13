from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from scripts.backtest_dashboard_data import CACHE_PATH, get_dashboard_payload, write_dashboard_cache


app = FastAPI(title="Backtest Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def current_mode() -> str:
    return os.getenv("BACKTEST_DASHBOARD_MODE", "live").strip().lower() or "live"


def current_payload() -> dict:
    return get_dashboard_payload(mode=current_mode(), cache_path=CACHE_PATH)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": current_mode()}


@app.get("/api/strategies")
def list_strategies() -> dict:
    payload = current_payload()
    return {
        "generated_at": payload["generated_at"],
        "strategies": [item["meta"] for item in payload["strategies"]],
    }


@app.get("/api/overview")
def overview(strategy_id: str) -> dict:
    payload = current_payload()
    strategy = payload["by_id"].get(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Unknown strategy_id: {strategy_id}")
    return {
        "generated_at": payload["generated_at"],
        "meta": strategy["meta"],
        "day_summaries": strategy["day_summaries"],
        "hold_stat_rows": strategy["hold_stat_rows"],
    }


@app.get("/api/day-detail")
def day_detail(strategy_id: str, date: str) -> dict:
    payload = current_payload()
    strategy = payload["by_id"].get(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Unknown strategy_id: {strategy_id}")
    detail = strategy["days"].get(date)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Unknown date for strategy: {date}")
    return {
        "generated_at": payload["generated_at"],
        "meta": strategy["meta"],
        "detail": detail,
    }


@app.post("/api/cache/rebuild")
def rebuild_cache() -> dict:
    payload = write_dashboard_cache(CACHE_PATH)
    return {
        "ok": True,
        "generated_at": payload["generated_at"],
        "cache_path": str(CACHE_PATH),
    }


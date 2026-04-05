import asyncio
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .model import DynamicTrustModel
from .schemas import (
    AccessContext,
    DecisionLogResponse,
    LoggedDecision,
    MetricsResponse,
    TrustScoreResponse,
    WeightsResponse,
    WeightsUpdateRequest,
)

app = FastAPI(
    title="AI-Based Dynamic Trust Scoring Engine",
    description=(
        "Reference implementation of an AI-powered dynamic trust scoring engine "
        "for Zero Trust Networks. It ingests contextual risk signals about a "
        "user, device, and resource, and produces a continuous trust score and "
        "decision (allow / challenge / deny)."
    ),
    version="0.1.0",
)

model = DynamicTrustModel()

# Serve the dashboard UI (static files).
_BASE_DIR = Path(__file__).resolve().parent
_WEB_DIR = _BASE_DIR / "web"
if _WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")

DB_PATH = (_BASE_DIR.parent / "data" / "trust_decisions.db").resolve()

# Simple in-memory decision log for observability / demo purposes.
_decision_log: List[LoggedDecision] = []
_MAX_LOG_SIZE = 500

# Optional background simulator to generate live events for the dashboard.
_sim_task: Optional[asyncio.Task] = None
_sim_running: bool = False

API_KEY = os.getenv("ZT_API_KEY", "zt-demo-key")


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                user_id TEXT,
                device_id TEXT,
                resource_id TEXT,
                decision TEXT,
                trust_score REAL,
                location TEXT,
                device_type TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        # Python 3.11+ can parse ISO strings with timezone.
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _decision_window(window_seconds: int) -> List[LoggedDecision]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    out: List[LoggedDecision] = []
    for d in _decision_log:
        dt = _parse_ts(d.timestamp)
        if dt is None:
            continue
        if dt >= cutoff:
            out.append(d)
    return out


def _compute_metrics(window_seconds: int) -> MetricsResponse:
    window_seconds = max(1, int(window_seconds))
    items = _decision_window(window_seconds)

    # Active sessions = unique (user_id, device_id) tuples.
    sessions = {(d.user_id, d.device_id) for d in items}
    blocked = sum(1 for d in items if d.decision == "deny")
    high_risk_users = {d.user_id for d in items if (d.trust_score or 0.0) < 0.4}
    avg = (
        sum((d.trust_score or 0.0) for d in items) / len(items)
        if items
        else 0.0
    )

    return MetricsResponse(
        window_seconds=window_seconds,
        active_sessions=len(sessions),
        high_risk_users=len(high_risk_users),
        average_trust_score=int(round(avg * 100)),
        blocked_attempts=blocked,
    )


def _log_decision(
    ctx: AccessContext,
    trust_score: float,
    decision: str,
    reasons: List[str],
    contributions: dict,
) -> None:
    entry = LoggedDecision(
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id=ctx.user_id,
        device_id=ctx.device_id,
        resource_id=ctx.resource_id,
        trust_score=trust_score,
        decision=decision,
        reasons=reasons,
        context=ctx,
        contributions=contributions,
    )
    _decision_log.append(entry)
    if len(_decision_log) > _MAX_LOG_SIZE:
        del _decision_log[: len(_decision_log) - _MAX_LOG_SIZE]

    # Persist to SQLite for durability (best-effort; errors are ignored).
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            ctx = entry.context
            conn.execute(
                """
                INSERT INTO decisions (
                    ts, user_id, device_id, resource_id, decision,
                    trust_score, location, device_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.timestamp,
                    entry.user_id,
                    entry.device_id,
                    entry.resource_id,
                    entry.decision,
                    float(entry.trust_score),
                    getattr(ctx, "location", None) if ctx is not None else None,
                    getattr(ctx, "device_type", None) if ctx is not None else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # We deliberately swallow DB errors so scoring is never blocked.
        pass


def verify_api_key(x_api_key: str = Header(default="")) -> None:
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    """
    Serve the Zero Trust dashboard UI.
    """
    index = _WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard files not found.")
    return FileResponse(index)


@app.get("/health")
async def health() -> dict:
    """
    Lightweight health-check endpoint.
    """
    return {"status": "ok"}


@app.post("/score", response_model=TrustScoreResponse)
async def score(
    ctx: AccessContext,
    _: None = Depends(verify_api_key),
) -> TrustScoreResponse:
    """
    Compute a dynamic trust score and decision for a given access context.
    """
    trust_score, decision, contributions = model.score(ctx)

    reasons = []

    if decision == "deny":
        reasons.append(
            "Overall trust score is low. Access denied according to Zero Trust policy."
        )
    elif decision == "challenge":
        reasons.append(
            "Trust score is moderate. Step-up authentication or additional checks required."
        )
    else:
        reasons.append("Trust score is high enough to allow access.")

    # Add a few simple human-readable explanations driven by feature values.
    if ctx.behavior_risk > 0.7:
        reasons.append("Recent behavior is highly anomalous.")
    if ctx.device_risk > 0.7:
        reasons.append("Device posture is risky (e.g., outdated patches or missing AV).")
    if ctx.user_risk > 0.7:
        reasons.append("User identity has a high risk score from identity provider.")
    if ctx.sensitive_resource:
        reasons.append("Target resource is sensitive, applying stricter thresholds.")
    if ctx.past_incidents > 2:
        reasons.append(
            "User or device has multiple prior security incidents on record."
        )

    # Optionally surface top contributing factors (positive values increase trust,
    # negative values reduce trust).
    sorted_contribs = sorted(
        ((k, v) for k, v in contributions.items() if not str(k).startswith("_")),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )
    top_factors = ", ".join(
        f"{name}={value:.3f}" for name, value in sorted_contribs[:3]
    )
    reasons.append(f"Top influencing factors (approximate): {top_factors}.")

    _log_decision(ctx, trust_score, decision, reasons, contributions)

    return TrustScoreResponse(trust_score=trust_score, decision=decision, reasons=reasons)


@app.get("/decisions", response_model=DecisionLogResponse)
async def list_decisions(
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(verify_api_key),
) -> DecisionLogResponse:
    """
    Return the most recent logged trust decisions (for observability / audit).

    Results are ordered from newest to oldest.
    """
    items = list(reversed(_decision_log[-limit:]))
    return DecisionLogResponse(items=items)


@app.get("/metrics", response_model=MetricsResponse)
async def metrics(
    window_seconds: int = Query(300, ge=10, le=3600),
    _: None = Depends(verify_api_key),
) -> MetricsResponse:
    """
    Real-time dashboard metrics computed from recent decisions.
    """
    return _compute_metrics(window_seconds)


@app.get("/config/weights", response_model=WeightsResponse)
async def get_weights(_: None = Depends(verify_api_key)) -> WeightsResponse:
    """
    Return current scoring weights.
    """
    return WeightsResponse(weights=model.get_weights())


@app.put("/config/weights", response_model=WeightsResponse)
async def put_weights(
    req: WeightsUpdateRequest,
    _: None = Depends(verify_api_key),
) -> WeightsResponse:
    """
    Update one or more scoring weights (in [0, 1]).
    """
    try:
        weights = model.update_weights(req.weights)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return WeightsResponse(weights=weights)


async def _sim_loop(rate_per_sec: float = 1.0) -> None:
    global _sim_running
    _sim_running = True
    users = ["U101", "U245", "U330", "U412", "U518", "U609", "U777"]
    locations = ["Delhi", "Mumbai", "Unknown"]
    devices: List[Tuple[str, str]] = [
        ("Laptop", "laptop-"),
        ("Desktop", "desktop-"),
        ("Android", "android-"),
    ]

    try:
        while _sim_running:
            u = random.choice(users)
            dev_type, prefix = random.choice(devices)
            ctx = AccessContext(
                user_id=u,
                device_id=f"{prefix}{random.randint(1, 9)}",
                device_type=dev_type,
                location=random.choice(locations),
                resource_id="prod-db",
                user_risk=random.random(),
                device_risk=random.random(),
                location_risk=random.random(),
                network_risk=random.random(),
                behavior_risk=random.random(),
                time_of_day=random.randint(0, 23),
                past_incidents=random.randint(0, 5),
                sensitive_resource=random.random() < 0.35,
            )

            trust_score, decision, contributions = model.score(ctx)

            reasons = []
            if decision == "deny":
                reasons.append(
                    "Overall trust score is low. Access denied according to Zero Trust policy."
                )
            elif decision == "challenge":
                reasons.append(
                    "Trust score is moderate. Step-up authentication or additional checks required."
                )
            else:
                reasons.append("Trust score is high enough to allow access.")

            _log_decision(ctx, trust_score, decision, reasons, contributions)
            await asyncio.sleep(max(0.05, 1.0 / max(0.1, rate_per_sec)))
    finally:
        _sim_running = False


@app.post("/simulate/start")
async def simulate_start(
    rate_per_sec: float = Query(1.0, ge=0.2, le=10.0),
    _: None = Depends(verify_api_key),
) -> dict:
    """
    Start a background traffic simulator (useful until real integrations exist).
    """
    global _sim_task, _sim_running
    if _sim_task is not None and not _sim_task.done():
        return {"running": True}
    _sim_running = True
    _sim_task = asyncio.create_task(_sim_loop(rate_per_sec=rate_per_sec))
    return {"running": True}


@app.post("/simulate/stop")
async def simulate_stop(_: None = Depends(verify_api_key)) -> dict:
    """
    Stop the background traffic simulator.
    """
    global _sim_task, _sim_running
    _sim_running = False
    if _sim_task is not None:
        try:
            await asyncio.wait_for(_sim_task, timeout=2.0)
        except Exception:
            pass
    return {"running": False}


@app.get("/simulate/status")
async def simulate_status(_: None = Depends(verify_api_key)) -> dict:
    return {"running": bool(_sim_task is not None and not _sim_task.done())}


@app.on_event("startup")
async def _auto_start_simulator() -> None:
    """
    Automatically start a background simulator so the dashboard is always live.

    For a real deployment you can remove this and drive /score from
    your actual Zero Trust gateway / IdP instead.
    """
    global _sim_task, _sim_running
    _init_db()
    if _sim_task is None or _sim_task.done():
        _sim_running = True
        _sim_task = asyncio.create_task(_sim_loop(rate_per_sec=1.5))

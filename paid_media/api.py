"""Read-only media analysis API; writes apply exclusively to local human-review records."""

import json
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from paid_media.analytics import diagnose
from paid_media.creative import CreativeBrief, draft
from paid_media.data import write_samples
from paid_media.experiments import recommendations, simulate
from paid_media.store import Conflict, Store

ROOT = Path(__file__).resolve().parents[1]


class TestResult(BaseModel):
    primary_kpi: str = Field(min_length=1, max_length=80)
    baseline_value: float = Field(ge=0, allow_inf_nan=False)
    variant_value: float = Field(ge=0, allow_inf_nan=False)
    control_sample: int = Field(gt=0)
    variant_sample: int = Field(gt=0)
    started_on: date
    ended_on: date
    outcome: Literal["Success", "Failure", "Inconclusive"]
    guardrails_passed: bool
    notes: str = Field(min_length=10, max_length=4000)

    @model_validator(mode="after")
    def validate_result(self):
        if self.ended_on < self.started_on:
            raise ValueError("End date must follow start date.")
        if self.outcome == "Success" and not self.guardrails_passed:
            raise ValueError("Success cannot be recorded when guardrails failed.")
        if (
            self.primary_kpi in {"CTR", "CVR", "MQL rate", "Event match rate", "Duplicate rate"}
            and max(self.baseline_value, self.variant_value) > 1
        ):
            raise ValueError("Rate values use fractions from 0 to 1.")
        return self


class Review(BaseModel):
    status: Literal["Approved", "Rejected", "Testing", "Completed"]
    reviewer: str = Field(min_length=1, max_length=120)
    notes: str = Field(min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)
    result: TestResult | None = None


def create_app(data_dir: Path | None = None, db_path: Path | None = None) -> FastAPI:
    data_dir = data_dir or Path(os.getenv("DATA_DIR", str(ROOT / "data")))
    db_path = db_path or Path(os.getenv("DB_PATH", str(ROOT / "runtime" / "reviews.sqlite")))

    @asynccontextmanager
    async def lifespan(application):
        if not (data_dir / "paid_media.csv").exists():
            write_samples(data_dir)
        frame = pd.read_csv(data_dir / "paid_media.csv")
        if not frame.synthetic.eq(True).all():
            raise ValueError("Only explicitly synthetic fixtures are supported.")
        application.state.frame = frame
        application.state.pages = json.loads((data_dir / "landing_pages.json").read_text(encoding="utf-8"))
        application.state.store = Store(db_path)
        default = diagnose(frame, application.state.pages)
        application.state.store.sync(recommendations(default))
        yield

    app = FastAPI(
        title="AI Paid Media Optimization & Experimentation Agent",
        version="1.0.0",
        description="Synthetic data only. Approvals are local records; no campaign execution endpoints.",
        lifespan=lifespan,
    )

    def analysis(end: date | None = None, window: int = 14, platform: str | None = None):
        frame = app.state.frame
        finish = end.isoformat() if end else str(frame.date.max())
        if finish < str(frame.date.min()) or finish > str(frame.date.max()):
            raise HTTPException(422, "End date must be inside the synthetic dataset range.")
        if platform:
            if platform not in set(frame.platform):
                raise HTTPException(422, "Unknown platform.")
            frame = frame[frame.platform == platform]
        return diagnose(frame, app.state.pages, finish, window)

    @app.get("/health")
    def health():
        return {"status": "ok", "synthetic_only": True, "campaign_execution_enabled": False}

    @app.get("/metadata")
    def metadata():
        f = app.state.frame
        return {
            "min_date": str(f.date.min()),
            "max_date": str(f.date.max()),
            "rows": len(f),
            "platforms": sorted(f.platform.unique().tolist()),
            "currency": "USD",
            "synthetic": True,
        }

    @app.get("/analysis")
    def report(end: date | None = None, window: int = Query(14, ge=7, le=28), platform: str | None = None):
        return analysis(end, window, platform)

    @app.get("/series")
    def series(platform: str | None = None):
        f = app.state.frame
        if platform:
            if platform not in set(f.platform):
                raise HTTPException(422, "Unknown platform.")
            f = f[f.platform == platform]
        return (
            f.groupby(["date", "platform"])[["spend", "conversions", "revenue", "clicks", "impressions"]]
            .sum()
            .reset_index()
            .to_dict("records")
        )

    @app.get("/recommendations")
    def list_recommendations(status: str | None = None):
        records = app.state.store.list()
        return [r for r in records if status is None or r["status"] == status]

    @app.post("/recommendations/generate")
    def generate(end: date | None = None, window: int = Query(14, ge=7, le=28)):
        records = recommendations(analysis(end, window))
        app.state.store.sync(records)
        return [app.state.store.get(r["id"]) for r in records]

    @app.patch("/recommendations/{rid}")
    def review(rid: str, request: Review):
        try:
            existing = app.state.store.get(rid)
            if request.result and request.result.primary_kpi != existing["experiment"]["primary_kpi"]:
                raise ValueError("Result primary KPI must match the pre-registered experiment.")
            return app.state.store.transition(
                rid,
                request.status,
                request.reviewer,
                request.notes,
                request.expected_version,
                request.result.model_dump(mode="json") if request.result else None,
            )
        except KeyError:
            raise HTTPException(404, "Recommendation not found.") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/recommendations/{rid}/history")
    def history(rid: str):
        try:
            return app.state.store.history(rid)
        except KeyError:
            raise HTTPException(404, "Recommendation not found.") from None

    @app.get("/budget-simulation")
    def budget(
        shift_fraction: float = Query(0.10, ge=0, le=0.30),
        end: date | None = None,
        window: int = Query(14, ge=7, le=28),
    ):
        return simulate(analysis(end, window), shift_fraction)

    @app.post("/creative/draft")
    def creative(brief: CreativeBrief):
        try:
            return draft(brief)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return app


app = create_app()

import logging
import os
from pathlib import Path
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool


logger = logging.getLogger("atlasflow.api")

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="AtlasFlow AI",
    description=(
        "LangGraph Multi-Agent Travel Planner with Supervisor, Guardrails, "
        "Human-in-the-Loop, and FastAPI Frontend"
    ),
    version="3.0.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TravelRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9_-]+$",
    )

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class ApprovalRequest(BaseModel):
    thread_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    approved: bool
    feedback: str = Field(default="", max_length=2_000)


def _start_travel_workflow(message: str, thread_id: str | None):
    """Import the heavyweight agent stack only when a workflow is requested."""
    from backend import run_travel_agent

    return run_travel_agent(user_input=message, thread_id=thread_id)


def _resume_travel_workflow(thread_id: str, approved: bool, feedback: str):
    from backend import resume_travel_agent

    return resume_travel_agent(
        thread_id=thread_id,
        approved=approved,
        feedback=feedback,
    )


def _safe_server_error(action: str, exc: Exception) -> JSONResponse:
    """Log diagnostic detail without exposing credentials or internals."""
    error_id = uuid.uuid4().hex[:10]
    logger.exception("%s failed [error_id=%s]", action, error_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": f"{action} failed. Reference: {error_id}",
        },
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.post("/api/travel")
async def travel_planner(request_data: TravelRequest):
    try:
        result = await run_in_threadpool(
            _start_travel_workflow,
            request_data.message,
            request_data.thread_id,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as exc:
        return _safe_server_error("Travel workflow", exc)


@app.post("/api/travel/approve")
async def approve_travel_plan(request_data: ApprovalRequest):
    try:
        if not request_data.approved and not request_data.feedback.strip():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Please provide revision feedback when rejecting the draft.",
                },
            )

        result = await run_in_threadpool(
            _resume_travel_workflow,
            request_data.thread_id,
            request_data.approved,
            request_data.feedback,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as exc:
        return _safe_server_error("Approval workflow", exc)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "atlasflow-ai",
        "version": app.version,
        "features": [
            "supervisor_agent",
            "input_guardrail",
            "human_in_the_loop",
        ],
    }


@app.get("/ready")
async def readiness_check():
    """Report whether core workflow dependencies are configured."""
    required = ("GROQ_API_KEY", "DATABASE_URL")
    missing = [name for name in required if not os.getenv(name)]
    status_code = 200 if not missing else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if not missing else "not_ready",
            "missing_configuration": missing,
        },
    )


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )

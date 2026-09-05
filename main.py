"""Vercel-compatible FastAPI entry (Streamlit stays in app.py for local runs)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from graph.build import build_graph
from graph.state import IncidentState
from integrations.slack import NoOpSlackClient, SlackClient
from llm.factory import create_client

load_dotenv()

_ROOT = Path(__file__).resolve().parent
_FIXTURES_DIR = _ROOT / "fixtures"
_TEMPLATES_DIR = _ROOT / "templates"

app = FastAPI(title="DevOps Incident Analysis Suite")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _fixture_names() -> list[str]:
    return sorted(p.name for p in _FIXTURES_DIR.glob("*.json"))


def _serialize_state(state: dict) -> dict:
    incidents = [
        {
            "id": i.id,
            "category": i.category,
            "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
            "summary": i.summary,
        }
        for i in state.get("incidents", [])
    ]
    remediations = [
        {
            "incident_id": r.incident_id,
            "source": r.source,
            "risk": r.risk,
            "effort": r.effort,
            "fix_steps": r.fix_steps,
            "rationale": r.rationale,
        }
        for r in state.get("remediations", [])
    ]
    tickets = [
        {
            "incident_id": t.incident_id,
            "ticket_id": t.ticket_id,
            "url": t.url,
            "summary": t.summary,
        }
        for t in state.get("tickets", [])
    ]
    errors = [{"node": e.node, "message": e.message} for e in state.get("errors", [])]
    notification = state.get("notification_result")
    notification_payload = None
    if notification is not None:
        notification_payload = {
            "summary_message_id": notification.summary_message_id,
            "thread_reply_ids": notification.thread_reply_ids,
            "error": notification.error,
        }
    return {
        "incidents": incidents,
        "remediations": remediations,
        "tickets": tickets,
        "cookbook": state.get("cookbook", ""),
        "errors": errors,
        "notification_result": notification_payload,
    }


def _run_analysis(raw_log: str, api_key: str, provider: str = "openrouter") -> dict:
    llm_client = create_client(provider, api_key)
    slack_token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    slack_channel = os.getenv("SLACK_CHANNEL_ID", "").strip()
    slack_client = (
        SlackClient(bot_token=slack_token, channel_id=slack_channel)
        if slack_token and slack_channel
        else NoOpSlackClient()
    )
    graph = build_graph(llm_client, slack_client)
    final_state: dict = {"errors": []}
    for chunk in graph.stream(IncidentState(raw_log=raw_log), stream_mode="updates"):
        for _node_name, node_output in chunk.items():
            final_state.update(node_output)
    return _serialize_state(final_state)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "fixtures": _fixture_names(),
            "has_env_key": bool(os.getenv("OPENROUTER_API_KEY")),
            "selected_fixture": "sample_mixed_severity.json",
            "result": None,
            "error": None,
        },
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    fixture: str = Form("(upload my own)"),
    raw_log: str = Form(""),
    api_key: str = Form(""),
):
    error = None
    result = None
    key = (api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
    log_text = raw_log.strip()
    if not log_text and fixture in _fixture_names():
        log_text = (_FIXTURES_DIR / fixture).read_text(encoding="utf-8")
    if not key:
        error = "OpenRouter API key required (sidebar field or OPENROUTER_API_KEY env)."
    elif not log_text:
        error = "Select a sample log or paste JSON log content."
    else:
        try:
            result = _run_analysis(log_text, key, provider="openrouter")
        except Exception as exc:  # noqa: BLE001 - surface to UI for demo
            error = str(exc)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "fixtures": _fixture_names(),
            "has_env_key": bool(os.getenv("OPENROUTER_API_KEY")),
            "selected_fixture": fixture,
            "result": result,
            "error": error,
        },
    )


@app.get("/health")
async def health():
    return {"ok": True}

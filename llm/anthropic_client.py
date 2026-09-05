from typing import Optional

from langchain_anthropic import ChatAnthropic

from graph.state import Incident, LogEvent, Remediation
from llm.client import ClassifyResult

_CLASSIFY_SYSTEM_PROMPT = (
    "You are a DevOps log classifier. Given structured log events, identify each "
    "distinct incident, its category (one of: oom, db_timeout, disk_full, "
    "deploy_failure, latency_spike, auth_failure, other), and its severity "
    "(critical, high, medium, low). Assign each incident a short unique id like 'inc-001'."
)

_RECOMMEND_SYSTEM_PROMPT = (
    "You are a DevOps remediation assistant. Given an incident and an optional known "
    "runbook entry, recommend fix steps, a rationale, a risk estimate, and an effort "
    "estimate. Prefer the runbook entry's fix_steps when one is given, and set source "
    "to 'runbook' in that case; otherwise reason generally and set source to 'llm'."
)


class AnthropicClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self._classify_model = ChatAnthropic(model=model, api_key=api_key).with_structured_output(ClassifyResult)
        self._recommend_model = ChatAnthropic(model=model, api_key=api_key).with_structured_output(Remediation)

    def classify(self, events: list[LogEvent]) -> list[Incident]:
        result = self._classify_model.invoke(
            [
                ("system", _CLASSIFY_SYSTEM_PROMPT),
                ("human", _events_to_prompt(events)),
            ]
        )
        return result.incidents

    def recommend(self, incident: Incident, runbook_entry: Optional[dict]) -> Remediation:
        return self._recommend_model.invoke(
            [
                ("system", _RECOMMEND_SYSTEM_PROMPT),
                ("human", _incident_to_prompt(incident, runbook_entry)),
            ]
        )


def _events_to_prompt(events: list[LogEvent]) -> str:
    lines = [f"{e.timestamp} [{e.level}] {e.service}: {e.message}" + (f" ({e.context})" if e.context else "") for e in events]
    return "Log events:\n" + "\n".join(lines)


def _incident_to_prompt(incident: Incident, runbook_entry: Optional[dict]) -> str:
    text = f"Incident: {incident.summary}\nCategory: {incident.category}\nSeverity: {incident.severity.value}"
    if runbook_entry:
        text += f"\nKnown runbook entry: {runbook_entry}"
    return text

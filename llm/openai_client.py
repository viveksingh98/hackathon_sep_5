from typing import Optional

from langchain_openai import ChatOpenAI

from graph.state import Incident, LogEvent, Remediation
from llm.anthropic_client import _events_to_prompt, _incident_to_prompt
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


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-5"):
        self._classify_model = ChatOpenAI(model=model, api_key=api_key).with_structured_output(ClassifyResult)
        self._recommend_model = ChatOpenAI(model=model, api_key=api_key).with_structured_output(Remediation)

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

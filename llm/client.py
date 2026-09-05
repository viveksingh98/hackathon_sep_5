from typing import Optional, Protocol

from pydantic import BaseModel

from graph.state import Incident, LogEvent, Remediation


class ClassifyResult(BaseModel):
    incidents: list[Incident]


class LLMClient(Protocol):
    def classify(self, events: list[LogEvent]) -> list[Incident]: ...

    def recommend(self, incident: Incident, runbook_entry: Optional[dict]) -> Remediation: ...

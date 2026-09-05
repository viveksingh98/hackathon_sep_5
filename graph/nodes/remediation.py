import json
from pathlib import Path
from typing import Callable

from graph.state import AgentError, IncidentState

_RUNBOOK_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge" / "runbook.json"


def run(llm_client) -> Callable[[IncidentState], dict]:
    runbook = _load_runbook()

    def _node(state: IncidentState) -> dict:
        remediations = []
        errors = list(state.errors)

        for incident in state.incidents:
            runbook_entry = runbook.get(incident.category)
            try:
                remediations.append(llm_client.recommend(incident, runbook_entry))
            except Exception as exc:  # noqa: BLE001 - node boundary must not raise
                errors.append(AgentError(node="remediation", message=f"{incident.id}: {exc}"))

        return {"remediations": remediations, "errors": errors}

    return _node


def _load_runbook() -> dict:
    if _RUNBOOK_PATH.exists():
        return json.loads(_RUNBOOK_PATH.read_text())
    return {}

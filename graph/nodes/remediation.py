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
                result = llm_client.recommend(incident, runbook_entry)
                # The prompt never carries incident.id and the model can misreport
                # its own grounding, so both fields are set from what the node
                # deterministically knows rather than trusted from the LLM.
                remediations.append(
                    result.model_copy(
                        update={
                            "incident_id": incident.id,
                            "source": "runbook" if runbook_entry else "llm",
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001 - node boundary must not raise
                errors.append(AgentError(node="remediation", message=f"{incident.id}: {exc}"))

        return {"remediations": remediations, "errors": errors}

    return _node


def _load_runbook() -> dict:
    if not _RUNBOOK_PATH.exists():
        return {}
    try:
        loaded = json.loads(_RUNBOOK_PATH.read_text())
    except Exception:  # noqa: BLE001 - a corrupt runbook must not break graph construction
        return {}
    return loaded if isinstance(loaded, dict) else {}

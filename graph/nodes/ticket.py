from typing import Callable

from graph.state import AgentError, IncidentState, Severity, Ticket


def run() -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        errors = list(state.errors)

        try:
            remediation_by_incident = {r.incident_id: r for r in state.remediations}
            tickets = []
            counter = 0

            for incident in state.incidents:
                if incident.severity != Severity.CRITICAL:
                    continue

                counter += 1
                ticket_id = f"MOCK-{1000 + counter}"
                remediation = remediation_by_incident.get(incident.id)

                description = incident.summary
                if remediation and remediation.fix_steps:
                    steps = "\n".join(f"- {step}" for step in remediation.fix_steps)
                    description = f"{description}\n\nRecommended fix:\n{steps}"

                tickets.append(
                    Ticket(
                        incident_id=incident.id,
                        ticket_id=ticket_id,
                        url=f"https://example-jira.mock/browse/{ticket_id}",
                        summary=incident.summary,
                        description=description,
                        labels=["auto-detected", incident.category],
                    )
                )
        except Exception as exc:  # noqa: BLE001 - node boundary must not raise
            errors.append(AgentError(node="ticket", message=str(exc)))
            return {"tickets": [], "errors": errors}

        return {"tickets": tickets, "errors": errors}

    return _node

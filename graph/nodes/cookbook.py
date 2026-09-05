from typing import Callable

from graph.state import AgentError, IncidentState, Severity

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
_FALLBACK_COOKBOOK = "# Incident Cookbook\n\n(generation failed)"


def run() -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        errors = list(state.errors)

        try:
            remediation_by_incident = {r.incident_id: r for r in state.remediations}
            ticket_by_incident = {t.incident_id: t for t in state.tickets}

            lines = ["# Incident Cookbook", ""]
            for severity in _SEVERITY_ORDER:
                incidents = [i for i in state.incidents if i.severity == severity]
                if not incidents:
                    continue

                lines.append(f"## {severity.value.title()}")
                lines.append("")
                for incident in incidents:
                    lines.append(f"### {incident.summary}")
                    remediation = remediation_by_incident.get(incident.id)
                    if remediation:
                        for step in remediation.fix_steps:
                            lines.append(f"- [ ] {step}")
                        lines.append(f"- Risk: {remediation.risk} · Effort: {remediation.effort}")
                    ticket = ticket_by_incident.get(incident.id)
                    if ticket:
                        lines.append(f"- Ticket: [{ticket.ticket_id}]({ticket.url})")
                    lines.append("")
        except Exception as exc:  # noqa: BLE001 - node boundary must not raise
            errors.append(AgentError(node="cookbook", message=str(exc)))
            return {"cookbook": _FALLBACK_COOKBOOK, "errors": errors}

        return {"cookbook": "\n".join(lines), "errors": errors}

    return _node

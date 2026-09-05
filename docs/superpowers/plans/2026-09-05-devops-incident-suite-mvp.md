# Multi-Agent DevOps Incident Analysis Suite — MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 1-day MVP of the Multi-Agent DevOps Incident Analysis Suite: a Streamlit app where a user uploads a structured JSON ops log, a fixed 5-agent LangGraph pipeline classifies incidents, proposes remediations, mocks a Jira ticket for critical incidents, synthesizes an actionable checklist, and posts a threaded Slack notification — with every step traceable live in the UI.

**Architecture:** A single Python process (Streamlit UI + LangGraph orchestrator, no separate backend). The graph is strictly linear: `log_reader → remediation → ticket → cookbook → notification`. Every node is a plain `(IncidentState) -> dict` function so it's testable without constructing a graph. LLM access goes through a small `LLMClient` protocol (Anthropic/OpenAI adapters), chosen at runtime.

**Tech Stack:** Python 3.10+, LangGraph, Streamlit, pydantic v2, `langchain-anthropic`, `langchain-openai`, `requests` (Slack `chat.postMessage`), `pytest`.

**Spec:** [docs/technical-specification.md](../../technical-specification.md) (implements [docs/requirements.md](../../requirements.md) and [docs/architecture.md](../../architecture.md))

## Global Constraints

- The LangGraph pipeline is **strictly linear** — no branching/fan-out edges. Ticket eligibility (`severity == critical`) is filtered *inside* the ticket node, not by skipping it in the graph.
- Jira ticket creation is **mocked** — no real Jira API call, no Jira credentials anywhere in the code.
- Slack notification **requires a bot token** (`SLACK_BOT_TOKEN`), not a bare Incoming Webhook, because threaded replies need the parent message's `ts`.
- Only structured JSON logs are supported (array of objects, or one JSON object per line) — no plain-text/syslog parsing.
- LLM provider is pluggable at runtime (Anthropic or OpenAI) — no single hardcoded default; API keys are session-only, never written to disk or logged.
- A failure in one node (Slack call, malformed log, LLM error) must not stop the rest of the pipeline — every node catches its own exceptions and records an `AgentError` instead of raising.
- No persistence beyond the current session; no auth layer.
- Field names in code must match `requirements.md`/`architecture.md` exactly: `Incident`, `Remediation`, `Ticket`, `IncidentState` with `raw_log`, `parsed_events`, `incidents`, `remediations`, `tickets`, `cookbook`, `notification_result`, `errors`.

---

## File Structure

```
graph/
  state.py                # pydantic models
  build.py                # build_graph()
  nodes/
    log_reader.py
    remediation.py
    ticket.py
    cookbook.py
    notification.py
llm/
  client.py                # LLMClient protocol + shared structured-output helper models
  anthropic_client.py
  openai_client.py
  factory.py                # create_client(provider, api_key)
integrations/
  slack.py                  # SlackClient
knowledge/
  runbook.json
fixtures/
  sample_oom.json
  sample_db_timeout.json
  sample_mixed_severity.json
tests/
  fakes.py                  # FakeLLMClient, FakeSlackClient
  test_state.py
  test_llm_client_protocol.py
  test_log_reader.py
  test_remediation.py
  test_ticket.py
  test_cookbook.py
  test_slack_client.py
  test_notification.py
  test_graph_end_to_end.py
  test_anthropic_client.py
  test_openai_client.py
  test_factory.py
app.py
requirements.txt
.env.example
README.md
```

---

### Task 1: Project scaffolding + core data models

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `graph/__init__.py`, `graph/state.py`
- Create: `tests/__init__.py`, `tests/test_state.py`

**Interfaces:**
- Produces: `Severity` (str enum: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), `LogEvent`, `Incident`, `Remediation`, `Ticket`, `NotificationResult`, `AgentError`, `IncidentState` — all `pydantic.BaseModel`, all importable from `graph.state`. `IncidentState` fields: `raw_log: str`, `parsed_events: list[LogEvent] = []`, `incidents: list[Incident] = []`, `remediations: list[Remediation] = []`, `tickets: list[Ticket] = []`, `cookbook: str = ""`, `notification_result: Optional[NotificationResult] = None`, `errors: list[AgentError] = []`.

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty file) and `tests/test_state.py`:

```python
from graph.state import (
    Severity,
    LogEvent,
    Incident,
    Remediation,
    Ticket,
    NotificationResult,
    AgentError,
    IncidentState,
)


def test_incident_state_defaults_are_empty():
    state = IncidentState(raw_log="{}")
    assert state.parsed_events == []
    assert state.incidents == []
    assert state.remediations == []
    assert state.tickets == []
    assert state.cookbook == ""
    assert state.notification_result is None
    assert state.errors == []


def test_incident_state_instances_do_not_share_default_lists():
    a = IncidentState(raw_log="{}")
    b = IncidentState(raw_log="{}")
    a.errors.append(AgentError(node="x", message="y"))
    assert b.errors == []


def test_incident_requires_severity_enum_value():
    incident = Incident(
        id="inc-001",
        category="oom",
        severity=Severity.CRITICAL,
        summary="Out of memory",
        source_events=[LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")],
    )
    assert incident.severity == Severity.CRITICAL
    assert incident.severity.value == "critical"


def test_remediation_optional_fields_default_none():
    remediation = Remediation(
        incident_id="inc-001",
        fix_steps=["Restart pod"],
        rationale="Known fix",
        risk="low",
        effort="low",
        source="runbook",
    )
    assert remediation.confidence is None


def test_ticket_holds_mock_reference_fields():
    ticket = Ticket(
        incident_id="inc-001",
        ticket_id="MOCK-1001",
        url="https://example-jira.mock/browse/MOCK-1001",
        summary="Out of memory",
        description="...",
        labels=["auto-detected", "oom"],
    )
    assert ticket.ticket_id == "MOCK-1001"


def test_notification_result_defaults():
    result = NotificationResult()
    assert result.summary_message_id is None
    assert result.thread_reply_ids == {}
    assert result.error is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'graph'` or similar — `graph/state.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `graph/__init__.py` (empty file).

Create `requirements.txt`:

```
streamlit
langgraph
langchain-anthropic
langchain-openai
pydantic
requests
python-dotenv
pytest
```

Create `.env.example`:

```bash
# Choose one at runtime in the sidebar; both may be set so either is available
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Slack (bot token — required for threaded replies)
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

Create `graph/state.py`:

```python
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LogEvent(BaseModel):
    timestamp: str
    service: str
    level: str
    message: str
    context: Optional[str] = None


class Incident(BaseModel):
    id: str
    category: str
    severity: Severity
    summary: str
    source_events: list[LogEvent] = Field(default_factory=list)


class Remediation(BaseModel):
    incident_id: str
    fix_steps: list[str]
    rationale: str
    risk: str
    effort: str
    source: str
    confidence: Optional[float] = None


class Ticket(BaseModel):
    incident_id: str
    ticket_id: str
    url: str
    summary: str
    description: str
    labels: list[str] = Field(default_factory=list)


class NotificationResult(BaseModel):
    summary_message_id: Optional[str] = None
    thread_reply_ids: dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None


class AgentError(BaseModel):
    node: str
    message: str


class IncidentState(BaseModel):
    raw_log: str
    parsed_events: list[LogEvent] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    remediations: list[Remediation] = Field(default_factory=list)
    tickets: list[Ticket] = Field(default_factory=list)
    cookbook: str = ""
    notification_result: Optional[NotificationResult] = None
    errors: list[AgentError] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_state.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example graph/__init__.py graph/state.py tests/__init__.py tests/test_state.py
git commit -m "feat: scaffold project and add IncidentState data models"
```

---

### Task 2: LLM client protocol + test fakes

**Files:**
- Create: `llm/__init__.py`, `llm/client.py`
- Create: `tests/fakes.py`
- Create: `tests/test_llm_client_protocol.py`

**Interfaces:**
- Consumes: `LogEvent`, `Incident`, `Remediation` from `graph.state` (Task 1).
- Produces: `LLMClient` protocol (`llm.client.LLMClient`) with `classify(events: list[LogEvent]) -> list[Incident]` and `recommend(incident: Incident, runbook_entry: dict | None) -> Remediation`. `ClassifyResult` pydantic wrapper (`llm.client.ClassifyResult`, one field `incidents: list[Incident]`) used later by the real adapters' structured-output calls. `tests.fakes.FakeLLMClient(classify_result=None, recommend_result=None)` implementing the protocol for use by every later node test.

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_client_protocol.py`:

```python
from graph.state import Incident, LogEvent, Remediation, Severity
from tests.fakes import FakeLLMClient


def test_fake_llm_client_classify_returns_configured_incidents():
    incident = Incident(
        id="inc-001",
        category="oom",
        severity=Severity.CRITICAL,
        summary="OOM crash",
        source_events=[],
    )
    client = FakeLLMClient(classify_result=[incident])

    result = client.classify([LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")])

    assert result == [incident]


def test_fake_llm_client_recommend_returns_configured_remediation():
    remediation = Remediation(
        incident_id="inc-001",
        fix_steps=["Restart pod"],
        rationale="Known fix",
        risk="low",
        effort="low",
        source="runbook",
    )
    client = FakeLLMClient(recommend_result=remediation)
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])

    result = client.recommend(incident, {"fix_steps": ["Restart pod"]})

    assert result == remediation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_client_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.fakes'`

- [ ] **Step 3: Write minimal implementation**

Create `llm/__init__.py` (empty file).

Create `llm/client.py`:

```python
from typing import Optional, Protocol

from pydantic import BaseModel

from graph.state import Incident, LogEvent, Remediation


class ClassifyResult(BaseModel):
    incidents: list[Incident]


class LLMClient(Protocol):
    def classify(self, events: list[LogEvent]) -> list[Incident]: ...

    def recommend(self, incident: Incident, runbook_entry: Optional[dict]) -> Remediation: ...
```

Create `tests/fakes.py`:

```python
from graph.state import Incident, LogEvent, Remediation


class FakeLLMClient:
    def __init__(self, classify_result=None, recommend_result=None):
        self._classify_result = classify_result if classify_result is not None else []
        self._recommend_result = recommend_result

    def classify(self, events: list[LogEvent]) -> list[Incident]:
        return self._classify_result

    def recommend(self, incident: Incident, runbook_entry) -> Remediation:
        if self._recommend_result is None:
            raise AssertionError("FakeLLMClient.recommend called without a configured recommend_result")
        return self._recommend_result


class FakeSlackClient:
    def __init__(self, ts_sequence=None, raise_on_call=None):
        self._ts_sequence = list(ts_sequence) if ts_sequence is not None else []
        self._raise_on_call = raise_on_call or set()
        self.calls = []

    def post_message(self, text, blocks=None, thread_ts=None):
        self.calls.append({"text": text, "blocks": blocks, "thread_ts": thread_ts})
        call_index = len(self.calls) - 1
        if call_index in self._raise_on_call:
            from integrations.slack import SlackError

            raise SlackError("mock_slack_failure")
        if self._ts_sequence:
            return self._ts_sequence.pop(0)
        return f"ts-{call_index}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_client_protocol.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add llm/__init__.py llm/client.py tests/fakes.py tests/test_llm_client_protocol.py
git commit -m "feat: add LLMClient protocol and test fakes"
```

---

### Task 3: Runbook knowledge file + Log Reader/Classifier node

**Files:**
- Create: `knowledge/runbook.json`
- Create: `graph/nodes/__init__.py`, `graph/nodes/log_reader.py`
- Create: `tests/test_log_reader.py`

**Interfaces:**
- Consumes: `IncidentState`, `LogEvent`, `Incident`, `AgentError` from `graph.state` (Task 1); `FakeLLMClient` from `tests.fakes` (Task 2).
- Produces: `graph.nodes.log_reader.run(llm_client) -> Callable[[IncidentState], dict]`. The returned callable's dict has keys `parsed_events`, `incidents`, `errors` (LangGraph partial-state-update convention).

- [ ] **Step 1: Write the failing test**

Create `tests/test_log_reader.py`:

```python
import json

from graph.nodes import log_reader
from graph.state import Incident, IncidentState, Severity
from tests.fakes import FakeLLMClient


def test_log_reader_parses_json_array_and_classifies():
    raw_log = json.dumps([
        {"timestamp": "t1", "service": "checkout-api", "level": "ERROR", "message": "OutOfMemoryError"},
    ])
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[])
    client = FakeLLMClient(classify_result=[incident])
    state = IncidentState(raw_log=raw_log)

    node = log_reader.run(client)
    result = node(state)

    assert len(result["parsed_events"]) == 1
    assert result["parsed_events"][0].service == "checkout-api"
    assert result["incidents"] == [incident]
    assert result["errors"] == []


def test_log_reader_recovers_partial_json_lines_and_records_error():
    raw_log = "\n".join([
        json.dumps({"timestamp": "t1", "service": "svc", "level": "INFO", "message": "ok"}),
        "not valid json",
        json.dumps({"timestamp": "t2", "service": "svc", "level": "ERROR", "message": "boom"}),
    ])
    client = FakeLLMClient(classify_result=[])
    state = IncidentState(raw_log=raw_log)

    node = log_reader.run(client)
    result = node(state)

    assert len(result["parsed_events"]) == 2
    assert len(result["errors"]) == 1
    assert "Dropped" in result["errors"][0].message


def test_log_reader_records_error_on_classify_failure():
    class RaisingClient:
        def classify(self, events):
            raise RuntimeError("model unavailable")

    state = IncidentState(raw_log=json.dumps([{"timestamp": "t", "service": "s", "level": "ERROR", "message": "m"}]))

    node = log_reader.run(RaisingClient())
    result = node(state)

    assert result["errors"][0].node == "log_reader"
    assert "model unavailable" in result["errors"][0].message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_log_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.nodes'`

- [ ] **Step 3: Write minimal implementation**

Create `knowledge/runbook.json`:

```json
{
  "oom": {
    "fix_steps": [
      "Increase the container memory limit",
      "Check for a memory leak introduced in the last deploy",
      "Add a memory-usage alert at 80% of the limit"
    ],
    "risk": "low",
    "effort": "low"
  },
  "db_timeout": {
    "fix_steps": [
      "Check the database connection pool size against current load",
      "Verify the database instance is not under CPU/IO pressure",
      "Add a circuit breaker around the affected query path"
    ],
    "risk": "medium",
    "effort": "medium"
  },
  "disk_full": {
    "fix_steps": [
      "Clear old log files or rotate logs more aggressively",
      "Increase the volume size",
      "Add a disk-usage alert at 85%"
    ],
    "risk": "low",
    "effort": "low"
  },
  "deploy_failure": {
    "fix_steps": [
      "Roll back to the last known-good deploy",
      "Check the failed deploy's build/test logs for the root cause",
      "Re-run the deploy once the underlying issue is fixed"
    ],
    "risk": "medium",
    "effort": "low"
  },
  "latency_spike": {
    "fix_steps": [
      "Check for a recent traffic spike or a slow downstream dependency",
      "Review recent deploys to the affected service",
      "Scale out the affected service if load-related"
    ],
    "risk": "medium",
    "effort": "medium"
  },
  "auth_failure": {
    "fix_steps": [
      "Check for an expired credential, certificate, or API key",
      "Verify the identity provider/auth service is healthy",
      "Rotate the affected credential if compromised"
    ],
    "risk": "high",
    "effort": "medium"
  }
}
```

Create `graph/nodes/__init__.py` (empty file).

Create `graph/nodes/log_reader.py`:

```python
import json
from typing import Callable

from graph.state import AgentError, IncidentState, LogEvent


def run(llm_client) -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        events, dropped = _parse_log(state.raw_log)
        errors = list(state.errors)
        if dropped:
            errors.append(AgentError(node="log_reader", message=f"Dropped {dropped} unparseable log line(s)"))

        try:
            incidents = llm_client.classify(events)
        except Exception as exc:  # noqa: BLE001 - node boundary must not raise
            errors.append(AgentError(node="log_reader", message=str(exc)))
            return {"parsed_events": events, "incidents": [], "errors": errors}

        return {"parsed_events": events, "incidents": incidents, "errors": errors}

    return _node


def _parse_log(raw_log: str) -> tuple[list[LogEvent], int]:
    raw_log = raw_log.strip()
    dropped = 0
    records: list[dict] = []

    try:
        parsed = json.loads(raw_log)
        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict):
            records = [parsed]
        else:
            raise ValueError("log content is not a JSON object or array")
    except (json.JSONDecodeError, ValueError):
        for line in raw_log.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                dropped += 1

    events: list[LogEvent] = []
    for record in records:
        try:
            events.append(
                LogEvent(
                    timestamp=str(record.get("timestamp", "")),
                    service=str(record.get("service", "unknown")),
                    level=str(record.get("level", "info")),
                    message=str(record.get("message", "")),
                    context=record.get("context"),
                )
            )
        except Exception:  # noqa: BLE001 - malformed record, count and skip
            dropped += 1

    return events, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_log_reader.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add knowledge/runbook.json graph/nodes/__init__.py graph/nodes/log_reader.py tests/test_log_reader.py
git commit -m "feat: add runbook knowledge file and log reader/classifier node"
```

---

### Task 4: Remediation node

**Files:**
- Create: `graph/nodes/remediation.py`
- Create: `tests/test_remediation.py`

**Interfaces:**
- Consumes: `IncidentState`, `Incident`, `Remediation`, `AgentError` from `graph.state`; `FakeLLMClient` from `tests.fakes`; reads `knowledge/runbook.json` (Task 3).
- Produces: `graph.nodes.remediation.run(llm_client) -> Callable[[IncidentState], dict]`, dict keys `remediations`, `errors`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_remediation.py`:

```python
from graph.nodes import remediation
from graph.state import Incident, IncidentState, Remediation, Severity
from tests.fakes import FakeLLMClient


def _incident(category="oom"):
    return Incident(id="inc-001", category=category, severity=Severity.CRITICAL, summary="OOM crash", source_events=[])


def test_remediation_calls_llm_with_runbook_entry_for_known_category():
    seen = {}

    class RecordingClient:
        def recommend(self, incident, runbook_entry):
            seen["runbook_entry"] = runbook_entry
            return Remediation(
                incident_id=incident.id,
                fix_steps=["Restart pod"],
                rationale="known fix",
                risk="low",
                effort="low",
                source="runbook",
            )

    state = IncidentState(raw_log="{}", incidents=[_incident("oom")])

    node = remediation.run(RecordingClient())
    result = node(state)

    assert seen["runbook_entry"] is not None
    assert "fix_steps" in seen["runbook_entry"]
    assert result["remediations"][0].source == "runbook"


def test_remediation_passes_none_runbook_entry_for_unknown_category():
    seen = {}

    class RecordingClient:
        def recommend(self, incident, runbook_entry):
            seen["runbook_entry"] = runbook_entry
            return Remediation(
                incident_id=incident.id,
                fix_steps=["Investigate"],
                rationale="general reasoning",
                risk="unknown",
                effort="unknown",
                source="llm",
            )

    state = IncidentState(raw_log="{}", incidents=[_incident("mystery_category")])

    node = remediation.run(RecordingClient())
    result = node(state)

    assert seen["runbook_entry"] is None
    assert result["remediations"][0].source == "llm"


def test_remediation_records_error_and_continues_on_failure():
    class RaisingClient:
        def recommend(self, incident, runbook_entry):
            raise RuntimeError("model timeout")

    state = IncidentState(raw_log="{}", incidents=[_incident("oom")])

    node = remediation.run(RaisingClient())
    result = node(state)

    assert result["remediations"] == []
    assert result["errors"][0].node == "remediation"
    assert "model timeout" in result["errors"][0].message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_remediation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.nodes.remediation'`

- [ ] **Step 3: Write minimal implementation**

Create `graph/nodes/remediation.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_remediation.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add graph/nodes/remediation.py tests/test_remediation.py
git commit -m "feat: add remediation node"
```

---

### Task 5: JIRA Ticket Agent (Mock) node

**Files:**
- Create: `graph/nodes/ticket.py`
- Create: `tests/test_ticket.py`

**Interfaces:**
- Consumes: `IncidentState`, `Incident`, `Remediation`, `Ticket`, `Severity` from `graph.state`.
- Produces: `graph.nodes.ticket.run() -> Callable[[IncidentState], dict]`, dict key `tickets`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ticket.py`:

```python
from graph.nodes import ticket
from graph.state import Incident, IncidentState, Remediation, Severity


def _incident(id_, severity):
    return Incident(id=id_, category="oom", severity=severity, summary=f"Issue {id_}", source_events=[])


def test_ticket_creates_mock_ticket_only_for_critical_incidents():
    state = IncidentState(
        raw_log="{}",
        incidents=[
            _incident("inc-001", Severity.CRITICAL),
            _incident("inc-002", Severity.HIGH),
            _incident("inc-003", Severity.MEDIUM),
        ],
    )

    node = ticket.run()
    result = node(state)

    assert len(result["tickets"]) == 1
    assert result["tickets"][0].incident_id == "inc-001"
    assert result["tickets"][0].ticket_id.startswith("MOCK-")
    assert "example-jira.mock" in result["tickets"][0].url


def test_ticket_includes_remediation_fix_steps_in_description_when_available():
    remediation = Remediation(
        incident_id="inc-001",
        fix_steps=["Restart pod", "Add alert"],
        rationale="known fix",
        risk="low",
        effort="low",
        source="runbook",
    )
    state = IncidentState(
        raw_log="{}",
        incidents=[_incident("inc-001", Severity.CRITICAL)],
        remediations=[remediation],
    )

    node = ticket.run()
    result = node(state)

    description = result["tickets"][0].description
    assert "Restart pod" in description
    assert "Add alert" in description


def test_ticket_handles_critical_incident_with_no_remediation():
    state = IncidentState(raw_log="{}", incidents=[_incident("inc-001", Severity.CRITICAL)])

    node = ticket.run()
    result = node(state)

    assert len(result["tickets"]) == 1
    assert result["tickets"][0].description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ticket.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.nodes.ticket'`

- [ ] **Step 3: Write minimal implementation**

Create `graph/nodes/ticket.py`:

```python
from typing import Callable

from graph.state import IncidentState, Severity, Ticket


def run() -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
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

        return {"tickets": tickets}

    return _node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ticket.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add graph/nodes/ticket.py tests/test_ticket.py
git commit -m "feat: add mock JIRA ticket agent node"
```

---

### Task 6: Cookbook Synthesizer node

**Files:**
- Create: `graph/nodes/cookbook.py`
- Create: `tests/test_cookbook.py`

**Interfaces:**
- Consumes: `IncidentState`, `Incident`, `Remediation`, `Ticket`, `Severity` from `graph.state`.
- Produces: `graph.nodes.cookbook.run() -> Callable[[IncidentState], dict]`, dict key `cookbook` (a Markdown string).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cookbook.py`:

```python
from graph.nodes import cookbook
from graph.state import Incident, IncidentState, Remediation, Severity, Ticket


def test_cookbook_orders_incidents_by_severity_and_includes_fix_steps():
    incidents = [
        Incident(id="inc-med", category="latency_spike", severity=Severity.MEDIUM, summary="Latency spike", source_events=[]),
        Incident(id="inc-crit", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[]),
    ]
    remediations = [
        Remediation(incident_id="inc-crit", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="runbook"),
    ]
    tickets = [
        Ticket(incident_id="inc-crit", ticket_id="MOCK-1001", url="https://example-jira.mock/browse/MOCK-1001", summary="OOM crash", description="d", labels=["oom"]),
    ]
    state = IncidentState(raw_log="{}", incidents=incidents, remediations=remediations, tickets=tickets)

    node = cookbook.run()
    result = node(state)
    text = result["cookbook"]

    assert text.index("OOM crash") < text.index("Latency spike")
    assert "Restart pod" in text
    assert "MOCK-1001" in text


def test_cookbook_handles_no_incidents():
    state = IncidentState(raw_log="{}")

    node = cookbook.run()
    result = node(state)

    assert "# Incident Cookbook" in result["cookbook"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cookbook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.nodes.cookbook'`

- [ ] **Step 3: Write minimal implementation**

Create `graph/nodes/cookbook.py`:

```python
from typing import Callable

from graph.state import IncidentState, Severity

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]


def run() -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
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

        return {"cookbook": "\n".join(lines)}

    return _node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cookbook.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add graph/nodes/cookbook.py tests/test_cookbook.py
git commit -m "feat: add cookbook synthesizer node"
```

---

### Task 7: Slack client + Notification node

**Files:**
- Create: `integrations/__init__.py`, `integrations/slack.py`
- Create: `graph/nodes/notification.py`
- Create: `tests/test_slack_client.py`, `tests/test_notification.py`

**Interfaces:**
- Consumes: `IncidentState`, `NotificationResult`, `Ticket` from `graph.state`; `FakeSlackClient` from `tests.fakes` (Task 2).
- Produces: `integrations.slack.SlackClient(bot_token, channel_id)` with `.post_message(text, blocks=None, thread_ts=None) -> str` (returns Slack's `ts`) and `integrations.slack.SlackError`. `graph.nodes.notification.run(slack_client) -> Callable[[IncidentState], dict]`, dict key `notification_result`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_slack_client.py`:

```python
import pytest

from integrations.slack import SlackClient, SlackError


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_post_message_returns_ts_on_success(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse({"ok": True, "ts": "1234.5678"})

    monkeypatch.setattr("integrations.slack.requests.post", fake_post)

    client = SlackClient(bot_token="xoxb-fake", channel_id="C123")
    ts = client.post_message(text="hello", thread_ts="1111.0000")

    assert ts == "1234.5678"
    assert captured["json"]["channel"] == "C123"
    assert captured["json"]["thread_ts"] == "1111.0000"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-fake"


def test_post_message_raises_slack_error_on_api_failure(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse({"ok": False, "error": "channel_not_found"})

    monkeypatch.setattr("integrations.slack.requests.post", fake_post)

    client = SlackClient(bot_token="xoxb-fake", channel_id="C123")

    with pytest.raises(SlackError, match="channel_not_found"):
        client.post_message(text="hello")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_slack_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations'`

- [ ] **Step 3: Write minimal implementation**

Create `integrations/__init__.py` (empty file).

Create `integrations/slack.py`:

```python
from typing import Optional

import requests

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"


class SlackError(Exception):
    pass


class SlackClient:
    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id

    def post_message(self, text: str, blocks: Optional[list] = None, thread_ts: Optional[str] = None) -> str:
        payload = {"channel": self.channel_id, "text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts

        response = requests.post(
            _SLACK_API_URL,
            headers={"Authorization": f"Bearer {self.bot_token}"},
            json=payload,
            timeout=10,
        )
        data = response.json()
        if not data.get("ok"):
            raise SlackError(data.get("error", "unknown_slack_error"))
        return data["ts"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_slack_client.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing test for the notification node**

Create `tests/test_notification.py`:

```python
from graph.nodes import notification
from graph.state import Incident, IncidentState, Severity, Ticket
from tests.fakes import FakeSlackClient


def _state_with_one_critical():
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[])
    ticket = Ticket(
        incident_id="inc-001",
        ticket_id="MOCK-1001",
        url="https://example-jira.mock/browse/MOCK-1001",
        summary="OOM crash",
        description="d",
        labels=["oom"],
    )
    return IncidentState(raw_log="{}", incidents=[incident], tickets=[ticket], cookbook="# Incident Cookbook")


def test_notification_posts_summary_then_one_thread_reply_per_ticket():
    slack_client = FakeSlackClient(ts_sequence=["1000.0001", "1000.0002"])
    state = _state_with_one_critical()

    node = notification.run(slack_client)
    result = node(state)

    notif = result["notification_result"]
    assert notif.summary_message_id == "1000.0001"
    assert notif.thread_reply_ids == {"inc-001": "1000.0002"}
    assert slack_client.calls[1]["thread_ts"] == "1000.0001"


def test_notification_records_error_when_summary_post_fails():
    slack_client = FakeSlackClient(raise_on_call={0})
    state = _state_with_one_critical()

    node = notification.run(slack_client)
    result = node(state)

    notif = result["notification_result"]
    assert notif.summary_message_id is None
    assert notif.error is not None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_notification.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.nodes.notification'`

- [ ] **Step 7: Write minimal implementation**

Create `graph/nodes/notification.py`:

```python
from typing import Callable

from graph.state import IncidentState, NotificationResult
from integrations.slack import SlackError


def run(slack_client) -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        try:
            summary_ts = slack_client.post_message(text="Incident analysis complete", blocks=_summary_blocks(state))
        except SlackError as exc:
            return {"notification_result": NotificationResult(error=str(exc))}

        thread_reply_ids = {}
        for ticket in state.tickets:
            try:
                reply_ts = slack_client.post_message(
                    text=f"Critical incident ticket: {ticket.ticket_id} — {ticket.url}",
                    thread_ts=summary_ts,
                )
                thread_reply_ids[ticket.incident_id] = reply_ts
            except SlackError as exc:
                thread_reply_ids[ticket.incident_id] = f"error: {exc}"

        return {
            "notification_result": NotificationResult(
                summary_message_id=summary_ts,
                thread_reply_ids=thread_reply_ids,
            )
        }

    return _node


def _summary_blocks(state: IncidentState) -> list:
    counts: dict[str, int] = {}
    for incident in state.incidents:
        counts[incident.severity.value] = counts.get(incident.severity.value, 0) + 1
    summary_line = ", ".join(f"{count} {severity}" for severity, count in counts.items()) or "no incidents found"

    return [
        {"type": "header", "text": {"type": "plain_text", "text": "Incident Analysis Complete"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Detected:* {summary_line}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": state.cookbook[:2900]}},
    ]
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_notification.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add integrations/__init__.py integrations/slack.py graph/nodes/notification.py tests/test_slack_client.py tests/test_notification.py
git commit -m "feat: add Slack client and notification node"
```

---

### Task 8: LangGraph wiring + end-to-end test

**Files:**
- Create: `graph/build.py`
- Create: `tests/test_graph_end_to_end.py`

**Interfaces:**
- Consumes: all five node modules (Tasks 3–7), `IncidentState` (Task 1), `FakeLLMClient`/`FakeSlackClient` (Task 2).
- Produces: `graph.build.build_graph(llm_client, slack_client)` returning a compiled LangGraph graph with `.invoke(IncidentState) -> IncidentState`-compatible behavior (LangGraph returns the merged state as a dict-like object; access via `result["incidents"]` etc., or wrap back into `IncidentState(**result)`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_end_to_end.py`:

```python
import json

from graph.build import build_graph
from graph.state import Incident, IncidentState, Remediation, Severity
from tests.fakes import FakeLLMClient, FakeSlackClient


def _make_llm_client():
    incidents = [
        Incident(id="inc-crit", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[]),
        Incident(id="inc-high", category="db_timeout", severity=Severity.HIGH, summary="DB timeout", source_events=[]),
    ]

    class SequencedClient(FakeLLMClient):
        def __init__(self):
            super().__init__(classify_result=incidents)
            self._remediations = {
                "inc-crit": Remediation(incident_id="inc-crit", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="runbook"),
                "inc-high": Remediation(incident_id="inc-high", fix_steps=["Check pool size"], rationale="r", risk="medium", effort="medium", source="runbook"),
            }

        def recommend(self, incident, runbook_entry):
            return self._remediations[incident.id]

    return SequencedClient()


def test_end_to_end_creates_ticket_only_for_critical_and_populates_cookbook():
    llm_client = _make_llm_client()
    slack_client = FakeSlackClient()
    graph = build_graph(llm_client, slack_client)

    raw_log = json.dumps([{"timestamp": "t", "service": "svc", "level": "ERROR", "message": "boom"}])
    result = graph.invoke(IncidentState(raw_log=raw_log))

    assert len(result["tickets"]) == 1
    assert result["tickets"][0].incident_id == "inc-crit"
    assert "OOM crash" in result["cookbook"]
    assert "DB timeout" in result["cookbook"]
    assert result["notification_result"].summary_message_id is not None
    assert result["notification_result"].thread_reply_ids == {"inc-crit": result["notification_result"].thread_reply_ids["inc-crit"]}


def test_end_to_end_slack_failure_still_leaves_cookbook_populated():
    llm_client = _make_llm_client()
    slack_client = FakeSlackClient(raise_on_call={0})
    graph = build_graph(llm_client, slack_client)

    raw_log = json.dumps([{"timestamp": "t", "service": "svc", "level": "ERROR", "message": "boom"}])
    result = graph.invoke(IncidentState(raw_log=raw_log))

    assert result["notification_result"].error is not None
    assert "OOM crash" in result["cookbook"]
    assert len(result["tickets"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph_end_to_end.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graph.build'`

- [ ] **Step 3: Write minimal implementation**

Create `graph/build.py`:

```python
from langgraph.graph import END, START, StateGraph

from graph.nodes import cookbook, log_reader, notification, remediation, ticket
from graph.state import IncidentState


def build_graph(llm_client, slack_client):
    graph = StateGraph(IncidentState)
    graph.add_node("log_reader", log_reader.run(llm_client))
    graph.add_node("remediation", remediation.run(llm_client))
    graph.add_node("ticket", ticket.run())
    graph.add_node("cookbook", cookbook.run())
    graph.add_node("notification", notification.run(slack_client))

    graph.add_edge(START, "log_reader")
    graph.add_edge("log_reader", "remediation")
    graph.add_edge("remediation", "ticket")
    graph.add_edge("ticket", "cookbook")
    graph.add_edge("cookbook", "notification")
    graph.add_edge("notification", END)

    return graph.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph_end_to_end.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add graph/build.py tests/test_graph_end_to_end.py
git commit -m "feat: wire the linear LangGraph pipeline"
```

---

### Task 9: Demo fixture log files

**Files:**
- Create: `fixtures/sample_oom.json`
- Create: `fixtures/sample_db_timeout.json`
- Create: `fixtures/sample_mixed_severity.json`
- Create: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: nothing (static data files); verified by parsing with `graph.nodes.log_reader._parse_log` (Task 3).
- Produces: three JSON fixture files under `fixtures/`, each a JSON array of raw log-event dicts (`timestamp`, `service`, `level`, `message`, optional `context`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixtures.py`:

```python
import json
from pathlib import Path

from graph.nodes.log_reader import _parse_log

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_sample_oom_parses_with_no_dropped_lines():
    raw_log = (_FIXTURES_DIR / "sample_oom.json").read_text()
    events, dropped = _parse_log(raw_log)
    assert dropped == 0
    assert len(events) >= 3
    assert any("OutOfMemory" in e.message or "OOM" in e.message for e in events)


def test_sample_db_timeout_parses_with_no_dropped_lines():
    raw_log = (_FIXTURES_DIR / "sample_db_timeout.json").read_text()
    events, dropped = _parse_log(raw_log)
    assert dropped == 0
    assert len(events) >= 2


def test_sample_mixed_severity_contains_multiple_services_or_messages():
    raw_log = (_FIXTURES_DIR / "sample_mixed_severity.json").read_text()
    events, dropped = _parse_log(raw_log)
    assert dropped == 0
    assert len(events) >= 5
    levels = {e.level for e in events}
    assert "ERROR" in levels or "FATAL" in levels
    assert "INFO" in levels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fixtures.py -v`
Expected: FAIL with `FileNotFoundError` (fixture files don't exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `fixtures/sample_oom.json`:

```json
[
  {"timestamp": "2026-09-05T02:14:01Z", "service": "checkout-api", "level": "INFO", "message": "Request received POST /checkout"},
  {"timestamp": "2026-09-05T02:14:03Z", "service": "checkout-api", "level": "WARN", "message": "Memory usage at 92% of container limit"},
  {"timestamp": "2026-09-05T02:14:05Z", "service": "checkout-api", "level": "ERROR", "message": "java.lang.OutOfMemoryError: Java heap space", "context": "at com.example.checkout.OrderProcessor.process(OrderProcessor.java:142)"},
  {"timestamp": "2026-09-05T02:14:06Z", "service": "checkout-api", "level": "FATAL", "message": "Container killed: OOMKilled (exit code 137)"}
]
```

Create `fixtures/sample_db_timeout.json`:

```json
[
  {"timestamp": "2026-09-05T03:02:11Z", "service": "orders-worker", "level": "INFO", "message": "Processing batch of 200 orders"},
  {"timestamp": "2026-09-05T03:02:41Z", "service": "orders-worker", "level": "WARN", "message": "Database query exceeded 5000ms, retrying"},
  {"timestamp": "2026-09-05T03:03:11Z", "service": "orders-worker", "level": "ERROR", "message": "psycopg2.OperationalError: connection timeout after 30s", "context": "connection pool exhausted (max_connections=20)"}
]
```

Create `fixtures/sample_mixed_severity.json`:

```json
[
  {"timestamp": "2026-09-05T04:00:00Z", "service": "web-frontend", "level": "INFO", "message": "Deploy v1.42.0 completed successfully"},
  {"timestamp": "2026-09-05T04:05:12Z", "service": "checkout-api", "level": "WARN", "message": "Memory usage at 92% of container limit"},
  {"timestamp": "2026-09-05T04:05:14Z", "service": "checkout-api", "level": "ERROR", "message": "java.lang.OutOfMemoryError: Java heap space", "context": "at com.example.checkout.OrderProcessor.process(OrderProcessor.java:142)"},
  {"timestamp": "2026-09-05T04:05:15Z", "service": "checkout-api", "level": "FATAL", "message": "Container killed: OOMKilled (exit code 137)"},
  {"timestamp": "2026-09-05T04:10:02Z", "service": "orders-worker", "level": "WARN", "message": "Database query exceeded 5000ms, retrying"},
  {"timestamp": "2026-09-05T04:10:32Z", "service": "orders-worker", "level": "ERROR", "message": "psycopg2.OperationalError: connection timeout after 30s", "context": "connection pool exhausted (max_connections=20)"},
  {"timestamp": "2026-09-05T04:15:00Z", "service": "web-frontend", "level": "INFO", "message": "Health check passed"}
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fixtures.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add fixtures/sample_oom.json fixtures/sample_db_timeout.json fixtures/sample_mixed_severity.json tests/test_fixtures.py
git commit -m "feat: add demo log fixtures"
```

---

### Task 10: Real LLM adapters (Anthropic + OpenAI)

**Files:**
- Create: `llm/anthropic_client.py`
- Create: `llm/openai_client.py`
- Create: `tests/test_anthropic_client.py`, `tests/test_openai_client.py`

**Interfaces:**
- Consumes: `LLMClient`, `ClassifyResult` from `llm.client` (Task 2); `Incident`, `Remediation`, `LogEvent` from `graph.state` (Task 1).
- Produces: `llm.anthropic_client.AnthropicClient(api_key, model="claude-sonnet-5")` and `llm.openai_client.OpenAIClient(api_key, model="gpt-5")`, both implementing `LLMClient` (`classify`, `recommend`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_anthropic_client.py`:

```python
from graph.state import Incident, LogEvent, Remediation, Severity
from llm import anthropic_client as mod
from llm.anthropic_client import AnthropicClient
from llm.client import ClassifyResult


class _FakeStructuredModel:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        return self._result


def _patch_chat_anthropic(monkeypatch, classify_result, recommend_result):
    monkeypatch.setattr(mod.ChatAnthropic, "__init__", lambda self, **kwargs: None)

    def fake_with_structured_output(self, schema):
        if schema is ClassifyResult:
            return _FakeStructuredModel(classify_result)
        return _FakeStructuredModel(recommend_result)

    monkeypatch.setattr(mod.ChatAnthropic, "with_structured_output", fake_with_structured_output)


def test_classify_returns_incidents_list(monkeypatch):
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    canned = ClassifyResult(incidents=[incident])
    _patch_chat_anthropic(monkeypatch, classify_result=canned, recommend_result=None)

    client = AnthropicClient(api_key="fake-key")
    result = client.classify([LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")])

    assert result == [incident]


def test_recommend_returns_remediation_directly(monkeypatch):
    remediation = Remediation(incident_id="inc-001", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="llm")
    _patch_chat_anthropic(monkeypatch, classify_result=None, recommend_result=remediation)

    client = AnthropicClient(api_key="fake-key")
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    result = client.recommend(incident, None)

    assert result == remediation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anthropic_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.anthropic_client'`

- [ ] **Step 3: Write minimal implementation**

Create `llm/anthropic_client.py`:

```python
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
```

Create `llm/openai_client.py` (same shape, OpenAI SDK):

```python
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
```

Create `tests/test_openai_client.py` (mirrors the Anthropic test, patching `ChatOpenAI`):

```python
from graph.state import Incident, LogEvent, Remediation, Severity
from llm import openai_client as mod
from llm.openai_client import OpenAIClient
from llm.client import ClassifyResult


class _FakeStructuredModel:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        return self._result


def _patch_chat_openai(monkeypatch, classify_result, recommend_result):
    monkeypatch.setattr(mod.ChatOpenAI, "__init__", lambda self, **kwargs: None)

    def fake_with_structured_output(self, schema):
        if schema is ClassifyResult:
            return _FakeStructuredModel(classify_result)
        return _FakeStructuredModel(recommend_result)

    monkeypatch.setattr(mod.ChatOpenAI, "with_structured_output", fake_with_structured_output)


def test_classify_returns_incidents_list(monkeypatch):
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    canned = ClassifyResult(incidents=[incident])
    _patch_chat_openai(monkeypatch, classify_result=canned, recommend_result=None)

    client = OpenAIClient(api_key="fake-key")
    result = client.classify([LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")])

    assert result == [incident]


def test_recommend_returns_remediation_directly(monkeypatch):
    remediation = Remediation(incident_id="inc-001", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="llm")
    _patch_chat_openai(monkeypatch, classify_result=None, recommend_result=remediation)

    client = OpenAIClient(api_key="fake-key")
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    result = client.recommend(incident, None)

    assert result == remediation
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anthropic_client.py tests/test_openai_client.py -v`
Expected: PASS (4 tests)

Note: these tests verify the adapters' plumbing (how they call `with_structured_output` and unwrap the result) without hitting the network. They do **not** verify real model output quality — spot-check that manually against the fixtures before the demo (see `technical-specification.md` §13).

- [ ] **Step 5: Commit**

```bash
git add llm/anthropic_client.py llm/openai_client.py tests/test_anthropic_client.py tests/test_openai_client.py
git commit -m "feat: add Anthropic and OpenAI LLM adapters"
```

---

### Task 11: LLM client factory

**Files:**
- Create: `llm/factory.py`
- Create: `tests/test_factory.py`

**Interfaces:**
- Consumes: `AnthropicClient` (Task 10), `OpenAIClient` (Task 10).
- Produces: `llm.factory.create_client(provider: str, api_key: str) -> LLMClient` — `provider` is `"anthropic"` or `"openai"`; raises `ValueError` otherwise.

- [ ] **Step 1: Write the failing test**

Create `tests/test_factory.py`:

```python
import pytest

from llm import factory


def test_create_client_anthropic_returns_anthropic_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(factory, "AnthropicClient", lambda api_key: sentinel)

    assert factory.create_client("anthropic", "key") is sentinel


def test_create_client_openai_returns_openai_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(factory, "OpenAIClient", lambda api_key: sentinel)

    assert factory.create_client("openai", "key") is sentinel


def test_create_client_unknown_provider_raises_value_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        factory.create_client("unknown", "key")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.factory'`

- [ ] **Step 3: Write minimal implementation**

Create `llm/factory.py`:

```python
from llm.anthropic_client import AnthropicClient
from llm.openai_client import OpenAIClient


def create_client(provider: str, api_key: str):
    if provider == "anthropic":
        return AnthropicClient(api_key=api_key)
    if provider == "openai":
        return OpenAIClient(api_key=api_key)
    raise ValueError(f"Unknown LLM provider: {provider}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_factory.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add llm/factory.py tests/test_factory.py
git commit -m "feat: add LLM client factory"
```

---

### Task 12: Streamlit app + README

**Files:**
- Create: `app.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `build_graph` (Task 8), `create_client` (Task 11), `SlackClient` (Task 7), `IncidentState` (Task 1), fixture files (Task 9).
- Produces: a runnable Streamlit app at `app.py`. No new importable interfaces — this is the top-level UI glue described in `technical-specification.md` §7.

- [ ] **Step 1: Write the smoke check**

There is no meaningful pytest for Streamlit UI code (per `technical-specification.md` §10, provider/Slack/UI correctness is verified manually during demo rehearsal, not via pytest). The testable deliverable for this task is an **import smoke check**:

Run: `python -c "import ast; ast.parse(open('app.py').read())"`
Expected (before `app.py` exists): FAIL with `FileNotFoundError`

- [ ] **Step 2: Write `app.py`**

```python
import json
from pathlib import Path

import streamlit as st

from graph.build import build_graph
from graph.state import IncidentState
from integrations.slack import SlackClient
from llm.factory import create_client

st.set_page_config(page_title="DevOps Incident Analysis Suite", layout="wide")

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_NODE_LABELS = {
    "log_reader": "Classifying incidents",
    "remediation": "Proposing remediations",
    "ticket": "Creating tickets (mock)",
    "cookbook": "Synthesizing checklist",
    "notification": "Posting to Slack",
}

st.markdown(
    """
    <div style="background:#07080a;color:#ffffff;padding:32px 24px;border-radius:12px;margin-bottom:24px;">
      <div style="font-size:12px;color:#9c9c9d;letter-spacing:.2px;">v0.1 · hackathon build</div>
      <div style="font-size:32px;font-weight:600;margin-top:4px;">
        Five agents read your logs. One incident, <span style="background:linear-gradient(90deg,#ffb347,#ff6b4a,#ff2f3a);-webkit-background-clip:text;background-clip:text;color:transparent;">resolved</span>.
      </div>
      <div style="font-size:15px;color:#b6b6b8;margin-top:8px;">
        Upload an ops log and watch five LangGraph agents classify every issue, propose a fix, open a ticket, and post the summary to Slack.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Configuration")
    provider = st.selectbox("LLM provider", ["anthropic", "openai"])
    api_key = st.text_input(f"{provider.title()} API key", type="password")
    st.divider()
    slack_bot_token = st.text_input("Slack bot token", type="password")
    slack_channel_id = st.text_input("Slack channel ID")

st.subheader("1. Choose a log")
fixture_names = sorted(p.name for p in _FIXTURES_DIR.glob("*.json"))
fixture_choice = st.selectbox("Use a sample log", ["(upload my own)"] + fixture_names)
uploaded_file = st.file_uploader("...or upload a JSON log file", type=["json"])

raw_log = None
if uploaded_file is not None:
    raw_log = uploaded_file.read().decode("utf-8")
elif fixture_choice != "(upload my own)":
    raw_log = (_FIXTURES_DIR / fixture_choice).read_text()

run_clicked = st.button("Analyze", disabled=raw_log is None or not api_key or not slack_bot_token or not slack_channel_id)

if run_clicked and raw_log is not None:
    llm_client = create_client(provider, api_key)
    slack_client = SlackClient(bot_token=slack_bot_token, channel_id=slack_channel_id)
    graph = build_graph(llm_client, slack_client)

    st.subheader("2. Live agent trace")
    status_boxes = {node: st.status(label, state="running") for node, label in _NODE_LABELS.items()}

    final_state = None
    for chunk in graph.stream(IncidentState(raw_log=raw_log), stream_mode="updates"):
        for node_name, node_output in chunk.items():
            box = status_boxes.get(node_name)
            if box is not None:
                box.update(state="complete")
            final_state = node_output

    st.subheader("3. Final report")
    if final_state is not None:
        cookbook_text = final_state.get("cookbook", "")
        tickets = final_state.get("tickets", [])
        notification_result = final_state.get("notification_result")

        st.markdown(cookbook_text)

        if tickets:
            st.markdown("**Mock tickets created:**")
            for ticket in tickets:
                st.markdown(f"- [{ticket.ticket_id}]({ticket.url}) — {ticket.summary}")

        if notification_result is not None:
            if notification_result.error:
                st.warning(f"Slack notification failed: {notification_result.error}")
            else:
                st.success("Slack summary + thread replies posted.")
```

- [ ] **Step 3: Run the smoke check**

Run: `python -c "import ast; ast.parse(open('app.py').read())"`
Expected: PASS (no output, exit code 0)

Also run: `pip install -r requirements.txt && python -c "import app"` in an environment with `ANTHROPIC_API_KEY`/etc. unset — this should fail only if a real import error exists (missing dependency, syntax error), not because keys are unset (the app only calls `create_client`/`SlackClient` after the button click).

- [ ] **Step 4: Write `README.md`**

```markdown
# Multi-Agent DevOps Incident Analysis Suite

Upload an ops log; five LangGraph agents classify incidents, propose fixes,
mock a Jira ticket for anything critical, synthesize a checklist, and post
the result to Slack — live, traceable, in one pass.

See [docs/requirements.md](docs/requirements.md), [docs/architecture.md](docs/architecture.md),
and [docs/technical-specification.md](docs/technical-specification.md) for the full design.

## Run it

\`\`\`bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys, or paste them into the sidebar at runtime
streamlit run app.py
\`\`\`

## Test it

\`\`\`bash
pytest -v
\`\`\`
```

- [ ] **Step 5: Commit**

```bash
git add app.py README.md
git commit -m "feat: add Streamlit app and README"
```

---

## Final Verification

- [ ] Run the full test suite: `pytest -v` — expect all tests from Tasks 1–11 passing (roughly 30 tests).
- [ ] Run `streamlit run app.py`, select the `sample_mixed_severity.json` fixture, enter a real (or dummy, to confirm the error path) API key and Slack bot token, click Analyze, and confirm: the live trace shows all five agents completing, the final report shows one mock ticket, and the cookbook lists both the critical and high-severity incidents.
- [ ] Cross-check against `requirements.md` §7 (Success Criteria / Demo Script) that every listed step is reachable in the running app.

## Known Plan Gaps (found by final whole-branch review, not fixed in this plan)

- **Cookbook de-duplication (Task 6) was never actually specified in this plan's code.** `technical-specification.md` §4.4 describes de-duplicating the cookbook by category (grouping incidents that share a category under one heading), but Task 6's sample code above only groups by severity and lists every incident individually — it does not de-duplicate by category at all. The implementation (correctly) followed this plan's code, not the technical spec's prose. Not a demo blocker with the shipped fixtures (no two incidents share a category), but a real log with repeated incident categories will show the same fix block multiple times instead of once. Fix in a follow-up: group `cookbook.py`'s severity buckets further by `incident.category` before rendering.

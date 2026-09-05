# Technical Specification: Multi-Agent DevOps Incident Analysis Suite

Implementation-level companion to [requirements.md](requirements.md) and [architecture.md](architecture.md). Where those two describe *what* and *why*, this document describes *how*: file structure, data models, function signatures, integration payloads, configuration, and the test/demo plan needed to actually build the 1-day MVP.

## 1. Project Structure

```
hackathon_sep_5/
├── app.py                     # Streamlit entrypoint (landing + upload + live trace + report)
├── graph/
│   ├── __init__.py
│   ├── state.py                # IncidentState + all pydantic models
│   ├── build.py                 # StateGraph construction (build_graph())
│   └── nodes/
│       ├── log_reader.py        # Log Reader / Classifier agent
│       ├── remediation.py       # Remediation agent
│       ├── ticket.py            # JIRA Ticket Agent (Mock)
│       ├── cookbook.py          # Cookbook Synthesizer agent
│       └── notification.py      # Notification agent (Slack)
├── llm/
│   ├── __init__.py
│   ├── client.py                 # LLMClient protocol
│   ├── anthropic_client.py
│   └── openai_client.py
├── integrations/
│   └── slack.py                  # Slack webhook/chat.postMessage wrapper
├── knowledge/
│   └── runbook.json               # Static category -> known-fix lookup
├── fixtures/
│   ├── sample_oom.json
│   ├── sample_db_timeout.json
│   └── sample_mixed_severity.json
├── tests/
│   ├── test_log_reader.py
│   ├── test_remediation.py
│   ├── test_ticket.py
│   ├── test_cookbook.py
│   ├── test_notification.py
│   └── test_graph_end_to_end.py
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   └── technical-specification.md   # this file
├── .env.example
└── requirements.txt
```

## 2. Data Models (`graph/state.py`)

All models are `pydantic.BaseModel`. Field names match the terminology used in `requirements.md` §4 and `architecture.md` §2 exactly, so the two docs and the code stay traceable to each other.

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel

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
    context: Optional[str] = None          # stack trace / extra fields, if present

class Incident(BaseModel):
    id: str                                 # e.g. "inc-001"
    category: str                           # oom | db_timeout | disk_full | deploy_failure | latency_spike | auth_failure | other
    severity: Severity
    summary: str
    source_events: list[LogEvent]

class Remediation(BaseModel):
    incident_id: str
    fix_steps: list[str]
    rationale: str
    risk: str                               # short free-text risk estimate
    effort: str                             # short free-text effort estimate (e.g. "low", "~30 min")
    source: str                             # "runbook" | "llm"
    confidence: Optional[float] = None      # 0-1, when the LLM provides one

class Ticket(BaseModel):
    incident_id: str
    ticket_id: str                          # mock id, e.g. "MOCK-1042"
    url: str                                # mock/fake link
    summary: str
    description: str
    labels: list[str]

class NotificationResult(BaseModel):
    summary_message_id: Optional[str] = None
    thread_reply_ids: dict[str, str] = {}   # incident_id -> Slack message id
    error: Optional[str] = None

class AgentError(BaseModel):
    node: str
    message: str

class IncidentState(BaseModel):
    raw_log: str
    parsed_events: list[LogEvent] = []
    incidents: list[Incident] = []
    remediations: list[Remediation] = []
    tickets: list[Ticket] = []
    cookbook: str = ""
    notification_result: Optional[NotificationResult] = None
    errors: list[AgentError] = []
```

## 3. LangGraph Wiring (`graph/build.py`)

Per `architecture.md` §2, the graph is **strictly linear** — no fan-out/fan-in, no conditional edges. Ticket eligibility is filtered *inside* the ticket node, not by skipping it.

```python
from langgraph.graph import StateGraph, START, END
from graph.state import IncidentState
from graph.nodes import log_reader, remediation, ticket, cookbook, notification

def build_graph(llm_client):
    g = StateGraph(IncidentState)
    g.add_node("log_reader", log_reader.run(llm_client))
    g.add_node("remediation", remediation.run(llm_client))
    g.add_node("ticket", ticket.run())
    g.add_node("cookbook", cookbook.run(llm_client))
    g.add_node("notification", notification.run())

    g.add_edge(START, "log_reader")
    g.add_edge("log_reader", "remediation")
    g.add_edge("remediation", "ticket")
    g.add_edge("ticket", "cookbook")
    g.add_edge("cookbook", "notification")
    g.add_edge("notification", END)
    return g.compile()
```

Each `nodes.*.run(...)` returns a plain function `(state: IncidentState) -> dict` (LangGraph's partial-state-update convention) so nodes stay independently unit-testable without constructing a graph. Every node wraps its body in `try/except`, appending an `AgentError` to `state.errors` and returning an otherwise-unchanged state on failure — this is the single mechanism behind the "one failure doesn't stop the run" requirement (`requirements.md` §6, `architecture.md` §7).

## 4. Agent Node Specs

### 4.1 `log_reader.run` (Log Reader / Classifier)
- Parses `raw_log` (JSON lines or a JSON array) into `LogEvent` objects.
- Calls the LLM once with the parsed events, asking for structured output: a list of `{ids of related events, category, severity, summary}`. Use `LLMClient.classify(events: list[LogEvent]) -> list[Incident]` (structured-output / tool-call mode, not free text, so the result parses reliably).
- On a JSON parse error: attempt line-by-line recovery (skip invalid lines, keep valid ones), record an `AgentError` noting how many lines were dropped.

### 4.2 `remediation.run` (Remediation)
- For each `Incident`, looks up `knowledge/runbook.json` by `category`. If found, passes the runbook entry into the LLM prompt as grounding context and sets `source="runbook"`; otherwise `source="llm"`.
- Calls `LLMClient.recommend(incident, runbook_entry) -> Remediation`.

`knowledge/runbook.json` shape:
```json
{
  "oom": {
    "fix_steps": ["Increase container memory limit", "Check for a leak in the last deploy", "Add a memory alert at 80% threshold"],
    "risk": "low",
    "effort": "low"
  },
  "db_timeout": { "...": "..." }
}
```

### 4.3 `ticket.run` (JIRA Ticket Agent — Mock)
- Pure function, no LLM call. For every `Incident` with `severity == Severity.CRITICAL`, builds a `Ticket`:
  - `ticket_id`: `f"MOCK-{1000 + counter}"` (counter scoped to the run).
  - `url`: `f"https://example-jira.mock/browse/{ticket_id}"` (clearly a mock domain — never a real Jira URL, so no one demoing this mistakes it for a live ticket).
  - `summary`/`description`: built from the `Incident.summary` and its matching `Remediation.fix_steps`.
- Cannot fail on a network call (there is none) — the only failure mode is a missing `Remediation` for a critical incident, handled by falling back to ticket text built from the `Incident` alone.

### 4.4 `cookbook.run` (Cookbook Synthesizer)
- Aggregates `incidents` + `remediations` + `tickets` into one Markdown document, incidents ordered `critical → high → medium → low`, each entry showing: issue summary, fix steps, risk/effort, and (if present) its mock ticket link.
- De-duplicates by `category`: incidents sharing a category are grouped under one heading with each severity instance listed underneath, rather than repeating the same fix text per incident.

### 4.5 `notification.run` (Notification)
- Posts once via `integrations/slack.py`: a summary card built from `cookbook`, then one threaded reply per `Ticket` (i.e., per critical incident) linking to that ticket's mock URL.
- Slack payload for the summary card (Incoming Webhook `POST` body):
  ```json
  { "text": "Incident analysis complete", "blocks": [ /* header + counts-by-severity + top remediations, built from `cookbook` */ ] }
  ```
- Thread replies use the `thread_ts` returned by the summary post (requires `chat.postMessage` with a bot token, not a bare Incoming Webhook, since webhooks don't return a `ts` to thread against — see §7 below).

## 5. LLM Provider Abstraction (`llm/client.py`)

```python
from typing import Protocol
from graph.state import LogEvent, Incident, Remediation

class LLMClient(Protocol):
    def classify(self, events: list[LogEvent]) -> list[Incident]: ...
    def recommend(self, incident: Incident, runbook_entry: dict | None) -> Remediation: ...
```

`AnthropicClient` and `OpenAIClient` in `llm/anthropic_client.py` / `llm/openai_client.py` implement this protocol using each SDK's structured-output / tool-calling mode (`langchain-anthropic`'s `with_structured_output(Incident)` equivalent) so `classify`/`recommend` always return parsed pydantic objects, never raw text the caller has to parse. The Streamlit sidebar constructs whichever adapter matches the user's provider + key selection and passes it into `build_graph()`.

## 6. Slack Integration (`integrations/slack.py`)

- Requires a **bot token** (`SLACK_BOT_TOKEN`), not just a webhook URL, because threaded replies need the parent message's `ts`, which `chat.postMessage` returns and Incoming Webhooks do not. `architecture.md` mentions both options; this spec settles on the bot-token path since threading is a hard requirement (`requirements.md` §5.5).
- Two calls: `chat.postMessage(channel, blocks=summary_blocks)` → capture `ts`; then one `chat.postMessage(channel, thread_ts=ts, text=...)` per critical incident.
- Wrapped in `try/except requests.RequestException` (or the Slack SDK's own exception type); on failure, returns a `NotificationResult(error=...)` rather than raising, so the orchestrator's error-handling contract (§7 of `architecture.md`) holds.

## 7. Streamlit App Structure (`app.py`)

| Section | Content |
|---|---|
| Hero / header | Static header banner using the visual language from the [landing hero design](https://claude.ai/code/artifact/57c38970-f20d-4170-b51f-06161760dc53) (dark warm-aurora aesthetic, product wordmark) — simplified/static (no live CSS animation) since it's rendered inside Streamlit, not a standalone HTML page. |
| Sidebar | LLM provider select (`Anthropic` / `OpenAI`) + API key input (`st.text_input(..., type="password")`, session-only); Slack bot token input. |
| Main — upload | `st.file_uploader` for a JSON log file, plus buttons to load one of the three bundled `fixtures/*.json` sample logs. |
| Main — live trace | On submit, calls `graph.stream(initial_state, stream_mode=["updates","custom"])` synchronously; one `st.status(...)` block per node (`log_reader`, `remediation`, `ticket`, `cookbook`, `notification`), each updated to "running" → "done"/"error" as its chunk arrives, with a one-line hand-off caption between them per `architecture.md` §6. |
| Main — final report | Renders `cookbook` as Markdown, a table of `tickets` (mock id + link), and the `notification_result` status. |

## 8. Configuration (`.env.example`)

```bash
# Choose one at runtime in the sidebar; both may be set so either is available
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Slack (bot token — required for threaded replies, see §6)
SLACK_BOT_TOKEN=
SLACK_CHANNEL_ID=
```

No Jira variables — ticketing is mocked (see §4.3).

## 9. Dependencies (`requirements.txt`)

```
streamlit
langgraph
langchain-anthropic
langchain-openai
pydantic
slack_sdk
python-dotenv
```

## 10. Testing Plan

- **Per-node unit tests** (`tests/test_*.py`): each node function called directly with a hand-built `IncidentState`, LLM calls mocked (return a fixed `Incident`/`Remediation`) so tests are deterministic and don't burn API credits. `test_ticket.py` and `test_cookbook.py` need no LLM mock since those nodes make no LLM calls.
- **`test_graph_end_to_end.py`**: runs `build_graph()` with a fake `LLMClient` and a fake Slack client against `fixtures/sample_mixed_severity.json` (which contains both critical and non-critical incidents), asserting: tickets exist only for critical incidents, the cookbook contains every incident, and a Slack failure (fake client raises) still leaves `cookbook` populated in the final state.
- No live-API integration tests are part of the 1-day scope; provider/Slack correctness is verified manually during the demo rehearsal instead.

## 11. Demo Fixtures

Three files under `fixtures/`, per `architecture.md` §10:
- `sample_oom.json` — single critical OOM incident (exercises the mock-ticket + Slack-thread path).
- `sample_db_timeout.json` — single high-severity DB timeout incident (exercises the no-ticket path).
- `sample_mixed_severity.json` — combination of the above plus a low-severity noise event, for the primary live demo run and for the end-to-end test.

## 12. Run Instructions

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in keys
streamlit run app.py
```

## 13. Open Risks / Follow-ups

- Threaded Slack replies require a bot token with `chat:write` scope in the target workspace; confirm this is provisioned before the demo (an Incoming-Webhook-only workspace cannot thread — see §6).
- LLM structured-output reliability (`classify`/`recommend` returning valid pydantic objects on the first try) should be spot-checked against the real fixture logs before the demo, since a malformed response is the most likely single point of failure in a live run.
- The landing hero design uses `git clone && streamlit run app.py` as its install caption — update it once the repo has a real public URL/name.

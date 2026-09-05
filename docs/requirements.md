# Requirements: Multi-Agent DevOps Incident Analysis Suite

## 1. Problem Statement / Motivation

When an incident hits, SREs and DevOps engineers spend a disproportionate amount of time on manual, repetitive work: reading raw logs, classifying what went wrong, remembering (or searching for) the right fix, telling the team, and filing a ticket so the fix doesn't get lost. Each of these steps is well-suited to an LLM agent, and chaining them together — with a human still in the loop, reviewing what the agents produced — turns a slow manual process into a few seconds of automated triage plus review.

2026 has seen "AI SRE" become a real product category (tools like Cleric and Resolve.ai investigate alerts autonomously across observability stacks). This project is not an attempt to compete with that category — it's a focused, demoable slice of the same idea: **upload a log, let a small team of specialized agents read it, explain it, recommend fixes, and push those fixes to the tools a team already uses (Slack, and — as a simulated stand-in for a real tracker — Jira).**

## 2. Goals & Non-Goals

**Goals**
- Demonstrate real multi-agent orchestration (LangGraph) over a concrete, useful workflow.
- Turn raw ops logs into classified issues, remediation guidance, a checklist, a Slack notification, and ticket references — automatically, in one pass.
- Make the agent pipeline's reasoning traceable: a reviewer should be able to see what each agent did and why, including visible hand-offs between agents.
- Ship a working, live-demoable app within a **1-day, 1-3 person build**.

**Non-Goals (this iteration)**
- Live/streaming ingestion from real infrastructure (CloudWatch, Kubernetes, syslog tailing, etc.) — the app works on uploaded log files only.
- Real third-party ticketing integration — Jira ticket creation is **simulated/mocked**, not a live API call (see [Assumptions & Constraints](#9-assumptions--constraints)).
- Multi-tenant auth, user accounts, or access control.
- Persistence of past analyses beyond the current session.
- Historical trend analysis / analytics dashboards.
- Vector-database-backed retrieval (RAG) over runbooks — remediation is grounded in a small static knowledge file instead.

## 3. Users & User Stories

**Primary persona:** an SRE/on-call engineer reviewing a batch of logs after an incident, or a DevOps lead doing a retro.

- As an SRE, I want to upload a log file and immediately see a categorized, severity-ranked list of issues, so I don't have to grep manually.
- As an SRE, I want each issue paired with a concrete fix and the reasoning behind it, so I can act with confidence.
- As an on-call lead, I want critical issues to auto-post to our Slack incident channel with a ticket reference, so nothing falls through the cracks.
- As a team, I want a synthesized checklist/runbook at the end, so we have a reusable artifact for the postmortem doc.
- As a demo viewer, I want to see the agents "hand off" work to each other, so the multi-agent architecture is legible, not a black box.

## 4. System Overview (Agents)

| # | Agent | Responsibility | Input | Output |
|---|---|---|---|---|
| 1 | Log Reader / Classifier | Parses raw log text, extracts structured fields, classifies each anomaly into a category + severity | Raw log text/file | List of `Incident` objects |
| 2 | Remediation | For each `Incident`, proposes fix(es) with rationale, risk, and effort | `Incident` | `Remediation` object |
| 3 | JIRA Ticket Agent (Mock) | For `severity == critical`, creates a **mocked** Jira ticket (no real Jira API call) and returns a ticket reference | `Incident` + `Remediation` | `Ticket` object |
| 4 | Cookbook Synthesizer | Aggregates all incidents + remediations + tickets into one de-duplicated, prioritized actionable checklist | All state | Cookbook (Markdown) |
| 5 | Notification | Formats and posts Slack messages: a summary card + one thread reply per critical incident, with ticket links | Cookbook + Tickets | Slack message IDs/links |
| — | Orchestrator | LangGraph `StateGraph` that sequences/fans-out/fans-in the above agents, handles conditional routing on severity | — | Full run trace |

> Named "JIRA Ticket Agent (Mock)" rather than "Slack Ticket" to keep the agent that fabricates a ticket reference distinct from the Notification agent that actually posts to Slack — the ticket reference it produces is what the Notification agent later links to.

## 5. Functional Requirements

### 5.1 Log Reader / Classifier Agent
- MUST accept an uploaded structured JSON log file (or set of JSON log lines).
- MUST extract structured events: timestamp, service/component, log level, message, and stack trace/context where present.
- MUST classify each significant event into an issue category (e.g., out-of-memory, database connection timeout, disk full, deployment failure, latency spike, auth failure, other/uncategorized).
- MUST assign a severity to each classified `Incident` (critical / high / medium / low).

### 5.2 Remediation Agent
- MUST take each `Incident` and produce recommended fix(es) with rationale, an estimated risk, and an estimated effort.
- MUST ground recommendations in a small internal runbook knowledge file where the issue category has a known entry, and fall back to general LLM reasoning otherwise (marking the source accordingly).
- SHOULD include a confidence indicator per recommendation.

### 5.3 JIRA Ticket Agent (Mock)
- MUST create a **simulated** ticket (summary, description, category/labels, mock ticket ID/link — no real Jira API call) for every `Incident` with `severity == critical`.
- MUST NOT create a ticket for high/medium/low severity incidents.
- MUST return a `Ticket` object (including the mock reference) for the Notification agent to link to.

### 5.4 Cookbook Synthesizer Agent
- MUST aggregate all incidents, remediations, and tickets for a run into a single de-duplicated, prioritized, actionable checklist (Markdown "Cookbook"), ordered by severity.
- MUST render the Cookbook in the UI as part of the final report.

### 5.5 Notification Agent
- MUST post one Slack summary card per analysis run, covering all detected issues and top remediations.
- MUST post one Slack thread reply per critical incident, including that incident's mock ticket link.
- MUST run after ticket creation, so ticket references are available to include in the Slack messages.

### 5.6 Orchestrator
- MUST run the agents above in a defined, traceable sequence per uploaded log, with fan-out/fan-in where steps are independent.
- MUST expose the live status/output of each agent to the UI as it executes, including visible hand-off between agents.
- MUST route ticket creation conditionally on `severity == critical`.
- MUST continue the pipeline (skipping only the failed step, not the whole run) if a single agent step fails, per the error-handling policy in the architecture doc.

## 6. Non-Functional Requirements

- **Performance:** the full pipeline should complete in a time appropriate for a live demo on logs up to a few thousand lines / a few MB.
- **Reliability:** a failure calling Slack must not prevent the rest of the pipeline (classification, remediation, ticketing, checklist) from completing and being shown to the user.
- **Security:** all API keys (LLM provider, Slack) are supplied via environment variables or in-session UI input only — never hardcoded, logged, or committed to source control.
- **Traceability:** every agent's input/output for a run must be visible in the UI so a reviewer can audit what happened and why.

## 7. Success Criteria / Demo Script

1. User opens the Streamlit app and selects an LLM provider (Anthropic or OpenAI) with an API key.
2. User uploads one of the provided sample JSON log files (or their own).
3. The UI shows each agent's step live as the pipeline runs, including visible hand-offs: parsing → classification → remediation → (mock) ticketing → checklist synthesis → Slack notification.
4. Critical incidents get a mock ticket reference; the UI shows the mock ticket ID/link for each.
5. A Slack summary card appears in the configured channel, with one thread reply per critical incident linking to its mock ticket.
6. The UI displays a final actionable Cookbook checklist covering all detected issues.

This end-to-end flow, completed live without manual intervention beyond the initial upload, is the definition of "done" for the hackathon demo.

## 8. Assumptions & Constraints

- LLM access is pluggable: the user chooses Anthropic or OpenAI at runtime and supplies their own API key; there is no single hardcoded default provider.
- A real Slack workspace (with an incoming webhook or bot token) is available at demo time.
- Jira ticket creation is **simulated in-app** — no real Jira account, project, or API token is required for the demo.
- Only structured JSON logs are supported in this iteration — plain-text/syslog-style logs are out of scope.
- The app is single-user, run locally, with no authentication layer.
- No data is persisted beyond the current browser session.

## 9. Out of Scope / Future Work

- Real Jira (or other tracker) API integration, replacing the current mocked ticket agent.
- Real vector-database-backed RAG over a larger runbook corpus.
- Live/streaming log ingestion from real infrastructure sources.
- Support for additional log formats (plain text, syslog, multi-format auto-detection).
- Persistence and a history/analytics dashboard across runs.
- Dynamic, LLM-routed supervisor orchestration in place of the fixed pipeline.
- Multi-tenant auth and role-based access control.

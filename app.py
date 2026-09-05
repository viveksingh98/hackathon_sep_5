import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from graph.build import build_graph
from graph.state import IncidentState
from integrations.slack import SlackClient
from llm.factory import create_client

load_dotenv()

st.set_page_config(page_title="DevOps Incident Analysis Suite", layout="wide")

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_NODE_LABELS = {
    "log_reader": "Classifying incidents",
    "remediation": "Proposing remediations",
    "ticket": "Creating tickets (mock)",
    "cookbook": "Synthesizing checklist",
    "notification": "Posting to Slack",
}
_AGENT_NAMES = {
    "log_reader": "Log Reader Agent",
    "remediation": "Remediation Agent",
    "ticket": "JIRA Ticket Agent",
    "cookbook": "Cookbook Agent",
    "notification": "Notification Agent",
}
_PROVIDER_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

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
    api_key = st.text_input(
        f"{provider.title()} API key",
        type="password",
        value=os.getenv(_PROVIDER_KEY_ENV[provider], ""),
    )
    st.divider()
    slack_bot_token = st.text_input("Slack bot token", type="password", value=os.getenv("SLACK_BOT_TOKEN", ""))
    slack_channel_id = st.text_input("Slack channel ID", value=os.getenv("SLACK_CHANNEL_ID", ""))
    st.caption("Values are pre-filled from your `.env` when present; edit them here to override.")

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
    node_order = list(_NODE_LABELS)
    trace = st.container()
    with trace:
        st.caption(f"→ starting with {_AGENT_NAMES[node_order[0]]}")

    final_state: dict = {}
    for chunk in graph.stream(IncidentState(raw_log=raw_log), stream_mode="updates"):
        for node_name, node_output in chunk.items():
            label = _NODE_LABELS.get(node_name, node_name)

            # A node signals failure either by growing state.errors or, for the
            # notification node, via notification_result.error.
            errors_before = len(final_state.get("errors", []))
            node_failed = len(node_output.get("errors", [])) > errors_before
            node_notification = node_output.get("notification_result")
            if node_notification is not None and node_notification.error:
                node_failed = True

            with trace:
                st.status(label, state="error" if node_failed else "complete")
                if node_name in node_order:
                    next_index = node_order.index(node_name) + 1
                    if next_index < len(node_order):
                        st.caption(f"→ passing to {_AGENT_NAMES[node_order[next_index]]}")
                    else:
                        st.caption("→ compiling final report")

            final_state.update(node_output)

    st.subheader("3. Final report")
    if final_state:
        cookbook_text = final_state.get("cookbook", "")
        tickets = final_state.get("tickets", [])
        notification_result = final_state.get("notification_result")
        errors = final_state.get("errors", [])

        for err in errors:
            st.warning(f"{err.node}: {err.message}")

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

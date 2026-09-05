# Multi-Agent DevOps Incident Analysis Suite

Upload an ops log; five LangGraph agents classify incidents, propose fixes,
mock a Jira ticket for anything critical, synthesize a checklist, and post
the result to Slack — live, traceable, in one pass.

See [docs/requirements.md](docs/requirements.md), [docs/architecture.md](docs/architecture.md),
and [docs/technical-specification.md](docs/technical-specification.md) for the full design.

## Run it (local Streamlit)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys, or paste them into the sidebar at runtime
streamlit run streamlit_app.py
```

`streamlit_app.py` loads `.env` on startup, so `OPENROUTER_API_KEY` (preferred for demo),
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, and optional `SLACK_BOT_TOKEN` /
`SLACK_CHANNEL_ID` pre-fill the sidebar fields. Anything you type in the sidebar
overrides them for that session; nothing is written back to disk.

Slack is optional — leave those fields blank to run classification, remediation,
mock tickets, and the cookbook without posting.

## Run it (Vercel / FastAPI)

Streamlit needs a persistent server, so Vercel hosting uses a thin FastAPI UI in
`main.py` that calls the same LangGraph agents.

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# or: vercel --prod   # after login / VERCEL_TOKEN, with OPENROUTER_API_KEY in project env
```

## Test it

```bash
pytest -v
```

# Multi-Agent DevOps Incident Analysis Suite

Upload an ops log; five LangGraph agents classify incidents, propose fixes,
mock a Jira ticket for anything critical, synthesize a checklist, and post
the result to Slack — live, traceable, in one pass.

See [docs/requirements.md](docs/requirements.md), [docs/architecture.md](docs/architecture.md),
and [docs/technical-specification.md](docs/technical-specification.md) for the full design.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys, or paste them into the sidebar at runtime
streamlit run app.py
```

`app.py` loads `.env` on startup, so `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`,
`SLACK_BOT_TOKEN`, and `SLACK_CHANNEL_ID` pre-fill the sidebar fields. Anything
you type in the sidebar overrides them for that session; nothing is written back
to disk.

## Test it

```bash
pytest -v
```

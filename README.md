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

## Test it

```bash
pytest -v
```

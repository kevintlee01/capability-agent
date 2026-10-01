# Computer-Use Automation System

A small, real, end-to-end "computer-use" system: an LLM-driven agent discovers
how to complete a goal against a live web surface, saves what it learned as a
typed, versioned **capability artifact**, and a separate, LLM-free **replay
engine** executes that artifact deterministically in production -- handling
real runtime errors, distinguishing business outcomes from hard failures, and
escalating to a human when it gets stuck.

See `/REPORT.md` for the design write-up (architecture, schema, determinism,
heterogeneity/multi-tenant story, escalation, safety, and cuts).

## Why a mock target app?

The assignment explicitly steers away from real bank systems and toward a
proxy target that still exercises "legacy, no-clean-DOM" problems. Rather than
risk a public site's ToS/rate limits, `mock_app/` is a small, intentionally
old-school server-rendered app (`Meridian Credit Union - Teller Console`):
table-based layout, no test IDs, no ARIA labels on form inputs -- it even
reproduces the "unlabeled textbox" problem that real legacy enterprise screens
have. It supports a multi-step flow (search -> member detail -> open
sub-account -> confirmation) with deterministic, ID-driven injected failure
modes (not found, permission denied, session timeout, validation error,
unexpected interstitial, hard server error) so replay error-handling can be
demonstrated on demand, repeatably.

## 1. Setup

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run playwright install chromium
cp .env.example .env   # then put your own GEMINI_API_KEY in .env (free tier: https://aistudio.google.com/apikey)
```

LLM provider is pluggable (`capability_agent/llm/`) -- Gemini is the default
since it has a free tier; OpenAI also works by setting `LLM_PROVIDER=openai`
and `OPENAI_API_KEY` instead.

No other services are required -- the target app is local.

## 2. Run the mock target app

```bash
uv run uvicorn mock_app.main:app --port 8731
```

Leave this running in its own terminal. Visit http://127.0.0.1:8731/ to look
around (try member IDs `10001`, `00000`, `40300`, `90000` -- see
`mock_app/data.py` for the full list of deterministic special cases).

## 3. Demo path: discover, then replay

All commands below assume `PYTHONPATH=.` (or run via `uv run python -m`).

**Discovery (real LLM run against the live mock app):**

```bash
uv run python -m capability_agent.cli discover \
  --name lookup_balance \
  --goal "Look up member 10001 and read their first account's balance" \
  --param member_id=10001
```

This drives a real Chromium browser (set `HEADLESS=false` in `.env` to watch
it), logs every observation/decision/action to `/evidence/discover-<id>/`,
and on success writes a versioned artifact to `/artifacts/lookup_balance/`.

**Deterministic replay (no LLM):**

```bash
uv run python -m capability_agent.cli replay \
  --name lookup_balance --param member_id=10001
```

Try `--param member_id=00000` (business outcome: not found) or
`--param member_id=40300` (business outcome: permission denied) to see the
result-type taxonomy in action without touching the LLM at all.

**List saved artifacts:**

```bash
uv run python -m capability_agent.cli list
```

## 4. Human-in-the-loop escalation demo

When the agent (or replay, for a risky step) can't safely proceed, it writes
`evidence/<run_id>/intervention.json` and blocks -- the same live browser
window stays open for a human to drive manually. In another terminal:

```bash
uv run python -m capability_agent.cli operator status <run_id>
# ... drive the visible browser window by hand ...
uv run python -m capability_agent.cli operator resume <run_id> --note "dismissed the fraud hold manually"
```

The run resumes in the same session and the human's navigation actions are
captured into the evidence log. See `REPORT.md` section 5 for the design.

## 5. Running the tests

```bash
uv run pytest -q
```

25 tests cover the artifact schema, guardrails (allowlist/risk/redaction),
the replay engine's templating and validation, the mock app's deterministic
outcomes, and the escalation control-transfer mechanism itself (a real
threaded test proves `request_intervention` blocks and resumes correctly --
no LLM or browser required for that part).

## 6. Running without live services

* Schema, guardrails, store, and escalation-control tests run with no
  external dependencies at all (no browser, no API key, no network).
* `tests/test_mock_app.py` exercises the target app in-process via FastAPI's
  `TestClient` -- no server process needed.
* Only `discover` (needs `OPENAI_API_KEY` + a live browser) and `replay`
  (needs a live browser, but no API key) touch Playwright.

## Project layout

```
mock_app/            the intentionally-legacy target application
capability_agent/
  artifact/           the capability schema + JSON storage
  discovery/          the LLM observe-decide-act loop + prompts
  replay/             the deterministic, LLM-free execution engine
  guardrails/          allowlist, risk classification, redaction
  escalation/          pause/resume control-transfer + mock operator CLI
  evidence/            structured, redacted run logging
  surface/             the shared Playwright session + observation builder
  llm/                 swappable LLM provider interface
  cli.py               typer CLI: discover / replay / list / operator
config/allowlist.yml  the permitted domains/routes/actions
artifacts/            saved capability artifacts (committed examples)
evidence/             discovery + replay run logs (committed examples)
tests/                pytest suite, one file per concern
scripts/              one-off authoring helpers (not part of the product)
```

## Cuts / known limitations

See `REPORT.md` section 7 for the full list and what we'd build next.

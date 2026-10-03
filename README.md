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
uv run playwright install chromium firefox webkit
cp .env.example .env   # then put your own GEMINI_API_KEY in .env (free tier: https://aistudio.google.com/apikey)
```

LLM provider is pluggable (`capability_agent/llm/`) -- Gemini
(`gemini-flash-lite-latest` by default) is the default since it has a free
tier; OpenAI also works by setting `LLM_PROVIDER=openai` and
`OPENAI_API_KEY` instead.

No other services are required -- the target app is local. Firefox and
WebKit are only needed if you want to run the cross-browser test suite
(Section 6); the product itself defaults to Chromium.

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

Two genuine live Gemini discovery runs are committed as evidence so you can
see this without burning API quota: `evidence/discover-ad48e232/` (member
lookup -> savings balance, 4 steps) and `evidence/discover-f3307ed3/`
(member lookup -> open a Checking sub-account -> confirmation, 7 steps,
autonomously discovered end to end). Both logs show the raw LLM responses,
reasoning, and actions, not a mocked transcript.

**Deterministic replay (no LLM):**

```bash
uv run python -m capability_agent.cli replay \
  --name lookup_balance --param member_id=10001
```

Try `--param member_id=00000` (business outcome: not found) or
`--param member_id=40300` (business outcome: permission denied) to see the
result-type taxonomy in action without touching the LLM at all.

**Second capability, exercising the rest of the error taxonomy:**
`open_sub_account` (hand-authored like `lookup_balance`, see
`scripts/author_open_sub_account_artifact.py`) demonstrates the paths
`lookup_balance` doesn't touch:

```bash
# risky step BLOCKED by default (artifact status is draft)
uv run python -m capability_agent.cli replay --name open_sub_account \
  --param member_id=20002 --param account_type=Savings --param nickname="Rainy Day" --param initial_deposit=50

# same call with --allow-risky: SUCCESS
... --allow-risky

# member 60000: fraud-hold interstitial is detected and auto-dismissed, still SUCCESS
... --param member_id=60000 --allow-risky

# member 70000: simulated backend crash, a genuine hard FAILURE (not a declared outcome)
... --param member_id=70000 --allow-risky

# blank nickname / zero deposit: two distinct validation-error BUSINESS OUTCOMES
... --param nickname="" --allow-risky
... --param initial_deposit=0 --allow-risky
```

**List saved artifacts:**

```bash
uv run python -m capability_agent.cli list
```

## 4. Mission Control dashboard (optional but pretty)

A dashboard for browsing saved capability artifacts and run evidence, plus
three real actions: running a *new* discovery, running a *replay*, and
resuming a pending escalation.

```bash
uv run uvicorn dashboard.main:app --port 8900
```

Open http://127.0.0.1:8900/ -- it reads straight from `/artifacts` and
`/evidence` on disk, so it reflects whatever `discover`/`replay` runs you've
done. If a run is paused on a human (`intervention.json` present), its detail
page shows the full context plus a working resume form, wired to the same
`operator resume` call the CLI uses.

The **official, graded demo path for this project is still the CLI commands
above** -- that's what Section 6 of the assignment asks for, and it's what
proves the agent loop and replay engine work without any UI in the way.
The dashboard's "Discover / Replay" page and the "Run Replay" form on each
artifact page are a convenience layer on top of that: clicking them calls
the exact same `DiscoveryAgent.run()` / `replay_artifact()` functions the CLI
calls, so there's no second code path to trust -- just a nicer way to show
the system to someone watching over your shoulder. Both still go through the
allowlist and the risky-step approval gate.

## 5. Human-in-the-loop escalation demo

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

## 6. Running the tests

```bash
uv run pytest -q
```

133 tests (the fast default suite -- cross-browser is excluded by a pytest
marker, see below), 99% statement coverage (the only two uncovered lines are
a `__main__` entrypoint guard and a deliberately-slow demo-only branch in the
mock app). Coverage is measured against real, mostly end-to-end behavior --
no LLM or browser calls are faked beyond a scripted fake LLM client standing
in for the network call itself:

* **Schema, guardrails, store, config, LLM client/factory, evidence logger,**
  **CLI wiring, dashboard routes** -- fast, isolated unit tests (mocks only
  at the actual network/SDK boundary).
* **Discovery agent loop** -- a real Playwright browser against the real
  mock app, driven by a scripted `FakeLLMClient`, covering success, failure,
  escalation + resume, malformed LLM output, step-budget exhaustion and its
  grace period (both recovering and giving up), every action type, and a
  hard LLM crash.
* **Replay engine** -- the real hand-authored artifacts replayed against a
  real mock app instance: success with extracted output, all three
  `lookup_balance` business outcomes, the risky-step gate (blocked, then
  allowed with `--allow-risky`), fraud-hold interstitial auto-recovery, a
  simulated hard backend failure, both `open_sub_account` validation
  outcomes, and an allowlist rejection.
* **Escalation control-transfer** -- a real threaded test proves
  `request_intervention` blocks and resumes correctly via the same files a
  human operator would touch.
* **Dashboard write actions** -- `trigger_discover`/`trigger_replay` mocked
  at the agent/engine boundary, plus the `/discover` and
  `/artifacts/.../replay` routes exercised end-to-end via `TestClient`.

To get the coverage report yourself:

```bash
uv run coverage run -m pytest -q && uv run coverage report -m
```

Playwright's sync API runs through greenlets, which standard `coverage.py`
tracing doesn't follow by default -- `pyproject.toml` sets
`[tool.coverage.run] concurrency = ["greenlet", "thread"]` so Playwright-driven
code (most of this project) is actually measured, not silently skipped.

### Cross-browser

```bash
uv run pytest tests/test_cross_browser.py -v -m cross_browser
```

The same deterministic replay flows (`lookup_balance` success,
`open_sub_account` fraud-hold interstitial recovery) run against Chromium,
Firefox, and WebKit via a `BrowserSession(engine=...)` parameter, proving the
locator/retry/interstitial logic isn't accidentally Chromium-specific. These
6 tests are tagged `@pytest.mark.cross_browser` and excluded from the default
`uv run pytest -q` run via `addopts` in `pyproject.toml` -- note the `-m
cross_browser` flag above is required even when targeting the file directly,
since `addopts` filters apply regardless of how tests are selected. Real
browser launches across 3 engines take a few minutes; budget accordingly.

## 7. Running without live services

* Schema, guardrails, store, and escalation-control tests run with no
  external dependencies at all (no browser, no API key, no network).
* `tests/test_mock_app.py` exercises the target app in-process via FastAPI's
  `TestClient` -- no server process needed.
* Only `discover` (needs `GEMINI_API_KEY` + a live browser) and `replay`
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
dashboard/            Mission Control: browse artifacts + run evidence
config/allowlist.yml  the permitted domains/routes/actions
artifacts/            saved capability artifacts (committed examples)
evidence/             discovery + replay run logs (committed examples)
tests/                pytest suite, one file per concern
scripts/              one-off authoring helpers (not part of the product)
```

## Cuts / known limitations

See `REPORT.md` section 7 for the full list and what we'd build next.

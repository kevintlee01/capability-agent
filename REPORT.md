# REPORT

## 1. Architecture

Single Python process, three swappable seams: **LLM provider** (`llm/`, a
one-method `complete(system, user) -> str` protocol so the agent loop never
imports an OpenAI type), **surface** (`surface/browser.py`, a thin Playwright
wrapper used identically by discovery, replay, and human handoff -- one
shared session, not three), and **target app** (any URL the allowlist
permits). Everything else is plain modules, no services, no queues: a single
successful run is cheap, and the brief explicitly says not to build scaling
infrastructure prematurely.

The discovery loop and the replay engine are **deliberately separate code
paths** that share only the surface layer and the artifact schema. This is
the central trade-off of the whole system: discovery is allowed to be messy,
adaptive, and LLM-latency-bound; replay must be boring, fast, and
LLM-free. Coupling them (e.g. "replay that falls back to the LLM on any
hiccup") would have been easier to build but would have undermined the one
property production actually needs: determinism. The optional "assisted
fallback" stretch goal is exactly this escape hatch, scoped tightly on
purpose -- we cut it (see Section 7).

Observation uses Playwright's `aria_snapshot()` (role + accessible name),
not raw HTML. This was chosen specifically because it is the one
representation that still works when there is no clean DOM, and it is also
available on desktop apps' accessibility trees -- so the same mental model
(and most of the locator code) survives the jump described in Section 4.

## 2. Artifact schema

A capability artifact (`artifact/schema.py`) is a contract for three readers
at once -- a human reviewer, the replay engine, and a calling AI agent -- so
none of them should need the raw model transcript. Key shape decisions:

* **`Locator` is a ranked list, not a single selector.** `primary` plus
  `fallbacks`, each a `(kind, value, role, nth)` tuple. Role+name is
  preferred (survives markup changes); `nth` is a deliberate, documented
  fallback for legacy controls that expose *no* accessible name at all --
  we hit this for real in our own mock app's unlabeled `<input>`, which is
  exactly the failure mode Section 1 warns about.
* **`known_outcomes` live on the artifact, not in the replay engine.** Only
  the discovery run (or a human reviewer) knows that "no such member" is a
  legitimate answer for *this* capability. A generic engine can't infer
  that, so the schema makes it first-class: a named outcome plus the
  locator that detects it.
* **Params/outputs are typed and declared, not inferred from the transcript**,
  so a calling agent has a real function signature, not a prompt to re-read.
* **`status: draft | approved`** and **`created_by`** exist cheaply now
  because they're nearly free fields that unlock real policy later (gating
  unattended replay, distinguishing human-authored from LLM-discovered
  capabilities) without a schema migration.
* Steps template literal values discovered at record time into
  `{{params.x}}` tokens (mechanical string substitution done by our code,
  not the LLM) -- this is what makes one recorded run reusable across many
  invocations instead of being a fixed transcript.

## 3. Determinism & error handling

Replay (`replay/engine.py`) never calls the LLM. Determinism comes from:
locator fallback chains resolved in a fixed order; a `RetryPolicy` per step
for transient waits (bounded attempts, fixed backoff -- no open-ended
retrying); and checking `known_outcomes` after every step, not just at the
end, because an outcome page can appear mid-flow and short-circuit the rest
of the script.

The spec draws a three-way line between business outcomes, recoverable
conditions, and hard failures, and the schema has a distinct first-class
mechanism for each rather than one generic "error" bucket:

* **Business outcomes** (`known_outcomes`): named, terminal, reported to the
  caller as data, not a crash.
* **Recoverable conditions**: two kinds, two mechanisms. Transient waits use
  `RetryPolicy` (bounded attempts, fixed backoff). Known interstitials (e.g.
  a fraud-review hold screen) use a new `interstitials` list -- each a
  `(detector, dismiss_action)` pair checked after every step; if the
  detector matches, the engine clicks the dismiss action, logs it to
  `recovered_conditions`, and continues the *same* run. This was missing
  from the first pass and is exactly the gap the spec calls out explicitly
  ("dismiss a known interstitial" is named separately from wait/retry) --
  validated live: replaying `open_sub_account` for a flagged member
  auto-dismisses the hold and still reaches the success checkpoint.
* **Hard failures**: anything else -- a checkpoint never met, a locator
  that never resolves, a risky step blocked by policy. Every failure path
  now captures a screenshot before returning (`FailureDetail.screenshot_path`),
  so "richer signal on failure" isn't just logged text -- validated by
  deliberately replaying into a simulated 500 and inspecting the captured
  page.

The result contract (`replay/outcomes.py`) is a closed three-way type:
`success` (with typed outputs), `business_outcome` (named, with a
description), or `failure` (step id, expected vs. observed, message,
screenshot). This was validated for real end to end across two artifacts:
`lookup_balance` (success with extracted balance, not-found and
permission-denied business outcomes) and `open_sub_account` (risky-step
block, interstitial auto-dismissal into success, two validation-error
business outcomes, and a genuine hard failure on a simulated backend crash).

## 4. Heterogeneity & multi-tenant

**Surface abstraction.** The seam is `BrowserSession` (surface) vs.
`Locator`/`Step` (recorded flow). A legacy web app with framesets is already
handled via `Locator.frame_path`. A desktop app would mean swapping
`surface/browser.py` for an OS-accessibility-API-backed implementation
(Windows UIA / macOS AX) behind the same four methods (`click`, `fill`,
`extract_text`, `is_visible`) and reusing `LocatorKind.ROLE` almost as-is,
since desktop accessibility trees use the same role/name concept Playwright
exposes for web. The artifact schema does not know what a browser is; it
only knows roles, names, and text -- that's intentional.

**Multi-tenant reuse.** Not built (out of scope per the brief), but the
schema does not paint us into a corner: `base_url` and any tenant-specific
literal (a route segment, a branded label) are exactly the things our
`{{params.x}}` templating already generalizes. A "base" artifact recorded
against one vendor-product tenant could be reused for another tenant running
the same product by (a) parameterizing `base_url` itself, and (b) layering a
per-tenant **override document** -- a small diff against the base artifact's
locators/values -- rather than re-recording. Drift detection falls out of
the replay contract for free: a tenant-specific replay that suddenly returns
unexpected `failure`s (checkpoint not met, locator unresolved) at a higher
rate than its peers is the signal that this tenant's version of the vendor
app has drifted and needs a reviewed override, which is exactly what the
optional "multi-run stability" stretch goal would surface numerically.

## 5. Escalation & handoff

**Detecting stuck** has two paths: the LLM can emit `action: "escalate"`
when it recognizes an unrecoverable ambiguity itself, and the loop
independently escalates when the step budget is exhausted (a hard backstop
so a confused model can't loop forever). Replay escalates differently: a
risky step on a non-approved artifact is blocked outright (Section 6)
rather than paused for a live decision, since unattended replay should not
be waiting on a human by design.

**Control transfer** is file-based and deliberately dumb:
`SessionControl.request_intervention()` writes `intervention.json`
(goal, step, reason, screenshot, URL) into the run's evidence directory and
blocks, polling for `resume.signal`. The mock operator CLI
(`operator status` / `operator resume`) and the Mission Control dashboard
(`dashboard/`, mostly a read-only view over the same `artifacts/`/`evidence/`
directories, plus demo-convenience buttons that just call the same
`DiscoveryAgent`/`replay_artifact` functions the CLI does) both only read and
write those same files for escalation purposes -- neither gets a
reference to the running process. This matters:
**the browser window itself never closes or hands off to anything new**; a
human at the same machine simply drives the same visible, already-open
Chromium window while automation is paused. That is the real "same session,
not a fresh one" requirement, achieved with no co-browsing infrastructure.

While paused, a `framenavigated` listener stays attached to the live
`Page`, so whatever the human does is still captured into the evidence log
-- instrumentation survives the handoff even though decision-making does
not. This was validated with a real threaded test
(`tests/test_escalation_control.py`): one thread blocks in
`request_intervention`, another resumes after a delay via the same
`operator_cli.resume()` path a human would use, and the blocked call
returns with the operator's note once the signal file appears.

**Who's in control** is answered by one predicate: `control.is_pending()`
(does `intervention.json` exist without a matching `resume.signal`?). No
separate state machine was needed.

## 6. Safety

An explicit, YAML-configured allowlist (`config/allowlist.yml`) is enforced
before every navigation (domain glob + route prefix) and before every action
type, independent of what the LLM decides to do -- a `GuardrailViolation`
stops the run rather than letting the model argue its way around policy.

Risk classification (`guardrails/risk.py`) defaults read-only actions
(navigate/extract/wait/assert) to safe and flags state-changing actions
whose own one-line description contains a keyword like "submit", "confirm",
"transfer", or "delete" as risky. Risky steps are blocked at replay time
unless the artifact's `status` is `approved` or the caller passes an
explicit `--allow-risky` override -- conservative by default, because an
unattended, scheduled replay should never silently perform an irreversible
action on an artifact nobody has reviewed yet.

Redaction (`guardrails/redact.py`) runs on every evidence-log write: field
names like `password`/`token`/`ssn` are replaced outright, and free text is
scrubbed for SSN/card-number/email patterns before it ever touches disk.

**Limits, honestly:** the risk classifier is a keyword heuristic on a
one-line description, not semantic understanding -- a risky action worded
blandly would slip through as "safe" today. The allowlist is route-prefix
based, not a full action/resource matrix. Both are acceptable depth for a
thin-but-real v1 and are called out explicitly in Section 7.

## 7. Cuts

What we deliberately left out, in rough priority order of "what we'd build
next":

* **Known-outcome *authoring* is manual, not LLM-discovered.** The
  discovery loop records steps and a checkpoint automatically; a human
  (or a follow-up prompt asking the model "what other outcomes did you
  notice?") currently adds `known_outcomes` and `interstitials` afterward.
  Auto-proposing these during discovery is the single highest-value next
  step.
* **Output/param type inference is string-only.** The schema supports
  number/boolean, but discovery always emits `"string"` today; a
  post-discovery typing pass would close this cheaply.
* **No confidence/approval scoring or multi-run stability signal** (both
  optional stretch goals) -- `status: draft/approved` exists in the schema
  as the seam, but nothing yet computes a reliability score to gate it
  automatically.
* **No assisted (LLM) fallback on replay failure** -- intentionally, to
  keep the determinism story unambiguous for this submission; the design
  would bound it to a single step, policy-checked, and logged as evidence
  if we added it.
* **No real desktop or multi-tenant implementation** -- out of scope per
  the brief; Section 4 is the design answer.
* **The operator surface is a dashboard, not a co-browsing console** --
  explicitly allowed by the scope note; it reads artifacts/evidence from
  disk and can trigger the one real resume action, but it is not a
  real-time view into the live browser session itself.
* **Risk classification is heuristic, not semantic** -- see Section 6.
* **`allowlist_scope` on the artifact is declarative only** -- it documents
  the routes a capability expects to touch, but only the global
  `config/allowlist.yml` policy is actually enforced at replay time today;
  cross-checking the two is a cheap follow-up.

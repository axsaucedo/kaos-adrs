# research-ref-3-1 — the create/verify-streamlit-app companion-skill pattern

Source: `EthicalML/agent-skills-marketplace`, branch `feat/streamlit-app-skills` ([PR #10](https://github.com/EthicalML/agent-skills-marketplace/pull/10)), local checkout at `/Users/asaucedo/Programming/ethical/agent-skills-marketplace`. Captured via `git show origin/feat/streamlit-app-skills:<path>` without checking out the branch. Paths: `plugins/workflow-automations/skills/create-streamlit-app/` and `plugins/workflow-automations/skills/verify-streamlit-app/`.

## Skill pairing

`create-streamlit-app` scaffolds a Streamlit + Polars local data app (`app.py`, `datasource.py`, `pyproject.toml`, `Makefile`, all templated from `assets/`). Its own `SKILL.md` ends the workflow section with "Verify it renders with the `verify-streamlit-app` skill before handing off" and its "When to use" section states outright: "To confirm the app actually renders, use the `verify-streamlit-app` skill." The pairing is declared in both directions — `verify-streamlit-app`'s frontmatter description ends "Pairs with create-streamlit-app." This is the whole companion-skill contract: the creation skill produces an artifact and explicitly hands off to a named verification skill rather than silently assuming the artifact works; the verification skill declares the pairing back so either skill can be discovered from the other.

## Three verification tiers (the key structural idea)

`verify-streamlit-app/SKILL.md` defines three explicit tiers and is emphatic that they must not be merged:

| Tier | What | When | Files |
|---|---|---|---|
| 1 — Manual loop (default) | Ad-hoc: screenshot, read page, read console errors, iterate | Active development | none — drive `assets/helpers.py` directly |
| 2 — Smoke check | One boot-and-render check: screenshot plus error scan, no behavioural assertions | Quick "does it come up clean?" gate | `assets/verify.py` |
| 3 — End-to-end (opt-in) | Real assertions on flows: select, click, assert content | User explicitly wants regression tests | `assets/tests_e2e_example.py` |

The SKILL.md states the default directly: "Default to tier 1 during development. Add tier 2 as a repeatable smoke gate. Only build tier 3 when the user asks for lasting tests." This is a manual-first, escalate-on-explicit-need structure — a harness is not built until there is a stated reason for it, matching the "never build a Playwright harness straight away" instruction in the ADR baseline (000-initial-request.md).

## Workflow (companion skill invoked after the app exists)

1. Scaffold the harness next to the app: copy `assets/helpers.py` and `assets/verify.py` into the app directory; generate `Makefile.verify` from `assets/Makefile.tmpl` (named to avoid clobbering the app's own `Makefile` from `create-streamlit-app` — run its targets with `make -f Makefile.verify <target>`). Copy `assets/tests_e2e_example.py` only for tier 3.
2. Install: `make -f Makefile.verify setup` → `uv pip install playwright pytest && uv run playwright install chromium`.
3. Start the app: `make -f Makefile.verify start-app`, which backgrounds `streamlit run app.py --server.headless true` and blocks in a poll loop (`for i in 1..60; curl -sf ... || sleep 1`) until the port answers — "Never drive the browser before the port answers."
4. Drive the browser through helpers: `create_browser()`, `goto(page, url)`, `screenshot(page, "name")`, `collect_errors(page)`.
5. Look at the screenshot and error output; if broken, fix and repeat from step 3. This is the tier-1 manual loop — explicitly a human/agent-in-the-loop iteration, not an automated assertion pass.
6. Gate repeatably with `make -f Makefile.verify verify` (tier 2, exits non-zero on any error).
7. Clean up: stop the app process, `make -f Makefile.verify clean`.

## The Makefile.tmpl shape (verify side)

```makefile
.PHONY: setup start-app verify test clean
PORT ?= 8501
URL ?= http://localhost:$(PORT)

setup:
	uv pip install playwright pytest
	uv run playwright install chromium

start-app:
	uv run streamlit run app.py --server.port $(PORT) --server.headless true & \
	for i in $$(seq 1 60); do \
	  curl -sf -o /dev/null $(URL) && exit 0; \
	  sleep 1; \
	done; \
	echo "app did not come up on $(URL)"; exit 1

verify:
	uv run python verify.py $(URL)

test:
	APP_URL=$(URL) uv run pytest tests_e2e_example.py

clean:
	rm -rf tmp/*.png
```

Notably minimal: five targets, one dependency install step, one boot-blocking loop, one smoke script, one pytest invocation. No CI wiring, no fixtures beyond a single `page` fixture in the tier-3 file.

## `verify.py` (tier 2 smoke check)

Boots the app URL, optionally waits for a content selector (for data-loading apps whose content appears after a query), screenshots, and calls `collect_errors(page)`. Exits 1 and prints every error if any are found; exits 0 with "OK: page rendered with no error markers" otherwise. No assertions about specific content — purely "did it render without exploding."

## `helpers.py` (the shared Playwright plumbing)

- `create_browser(headless=True)` launches headless Chromium, wires `page.on("console", ...)` and `page.on("pageerror", ...)` listeners into a module-level `_DIAGNOSTICS` list before any navigation — so JS errors are captured even if they fire before an explicit check.
- `ERROR_MARKERS` is a plain list of substrings (`"Traceback (most recent call last)"`, `"ModuleNotFoundError"`, `"NameError"`, `"KeyError"`, `"AttributeError"`, `"RecursionError"`, `"maximum recursion depth"`, `"streamlit.errors"`, `"Uncaught"`, `"TypeError:"`, `"ValueError:"`) scanned against page text — a deliberately low-tech signal, not a parser.
- `goto(page, url, wait_selector=".stApp")` waits for the Streamlit app shell first, since Streamlit paints `.stApp` instantly but data-loading content renders later; a screenshot on the shell alone risks catching an empty page. `wait_for_content()` is offered separately for callers that need a specific widget selector present.
- Streamlit-specific selector guidance embedded directly in `SKILL.md`: address widgets by label/role (survives reruns) not CSS class; `st.text_input` requires pressing Enter to commit (`fill_input` helper does this); multiselect needs click + keyboard type + Enter; dataframe rows are not buttons, click a pixel offset instead.
- Screenshots and scratch files live under a project-local `tmp/` directory, gitignored — "Do not use the system temp directory." This mirrors the ADR's `./tmp` convention exactly, just scoped to the app directory rather than the docs-authoring session.

## `tests_e2e_example.py` (tier 3 — explicitly opt-in and a *starting point*)

```python
def test_app_loads(page):
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator(".stApp")).to_be_visible()

def test_table_renders(page):
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_selector(".stDataFrame", timeout=30_000)
    expect(page.locator(".stDataFrame")).to_be_visible()

def test_filter_flow(page):
    """Example: type into a text filter and assert the app reruns cleanly."""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.get_by_label("Filter by term").fill("a")
    expect(page.locator(".stApp")).to_be_visible()
```

The module docstring is explicit: "This is a *starting point* — add assertions specific to your app's flows using Streamlit-aware selectors. Do not merge this with verify.py." Even the tier-3 example leans workflow-shaped (`test_filter_flow` types into a filter and asserts the app survives a rerun) rather than a trivial input/output equality check — consistent with the ADR's "avoid 1+1=2 tests" instruction, though this is a smoke/interaction check rather than a deep multi-step workflow assertion.

## What the RPI plugin should lift directly

- The tiered structure (manual loop default → smoke gate → opt-in e2e) as the canonical shape for *any* verification companion skill, not just Streamlit.
- The "pairs with X" cross-reference convention in both SKILL.md frontmatter descriptions.
- The boot-blocking poll loop pattern in the Makefile (never race the browser against server startup).
- The project-local, gitignored `tmp/` convention for screenshots/scratch artifacts.
- The instruction to keep tiers separate (never merge smoke check and e2e) and to only build tier 3 on explicit user request.

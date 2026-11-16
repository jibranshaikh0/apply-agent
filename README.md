# apply-agent

An agentic workflow for applying to US new-grad / intern software roles at
volume, with a human clicking the final submit button.

- **Roles source:** [Job Alerts by Herakraft](https://recruiting.herakraft.co) -
  open intern/new-grad roles polled from employers' own career sites
  (Workday, Greenhouse, Ashby, Lever, ...). Keyless free REST API plus an MCP
  server.
- **Filling:** applicant facts are written once in `answers/profile.json`;
  form labels are mapped to answers **in code**; an OpenAI model is only the
  fallback classifier for unmapped labels and can never invent data.
- **Safety:** a mandatory second pass re-reads every filled field, and a
  code-enforced guard stops the agent before any final submit.

## Setup

Requires Python 3.10+ (stdlib only, no pip install needed).

```bash
cp answers/profile.template.json answers/profile.json
# fill in answers/profile.json - it is gitignored and must never be committed
export OPENAI_API_KEY=...   # only used for unmapped-label classification
```

Optional, for Claude Code: the repo ships `.mcp.json` pointing at the Job
Alerts MCP server (`https://recruiting.herakraft.co/mcp`), so role search is
also available as MCP tools (`search_roles`, `get_role`, `list_tracks`, ...).

## Docker

Everything runs in one image (stdlib app plus Playwright/Chromium for the browser layer); no secrets or applicant data are
baked in. Build once:

```bash
docker build -t apply-agent .
```

Search roles (writes into a mounted `./out`):

```bash
mkdir -p out
docker run --rm -v "$PWD/out:/app/out" apply-agent \
  src/roles.py --level new-grad --track swe --grad 2027 --limit 60 --out out/shortlist.json
```

Build a fill plan. `answers/profile.json` (gitignored) is bind-mounted at
runtime and the OpenAI key passes through the environment - neither is in
the image:

```bash
docker run --rm \
  -v "$PWD/answers/profile.json:/app/answers/profile.json:ro" \
  -v "$PWD/fields.json:/app/fields.json:ro" \
  -v "$PWD/out:/app/out" \
  -e OPENAI_API_KEY \
  apply-agent src/fill.py fields.json \
    --profile answers/profile.json --out out/fill-plan.json
```

With no key mounted, run `--no-model` for code-only mapping. The
stop-before-submit guard and the second-pass verify behave exactly as
outside the container. CI (`.github/workflows/docker.yml`) rebuilds the
image on every push and runs the unit tests plus guard and fill smoke
checks inside it.

## Usage

Search roles (2027 new-grad SWE example):

```bash
python src/roles.py --level new-grad --track swe --grad 2027 --limit 60 --out shortlist.json
```

Fill an application form: the agent dumps the page's form fields to JSON, then

```bash
python src/fill.py fields.json --profile answers/profile.json --out fill-plan.json
```

`fill.py` resolves every field to a value (code mapping first, OpenAI
fallback second), and lists fields it could not map so a human can answer
them. After filling, the agent re-reads the page and calls
`verify_filled()` for the mandatory second pass.

## Browser layer

`src/browser.py` drives headless Chromium via Playwright (`pip install
playwright && playwright install chromium`; the Docker image already has
both). By default it only opens `localhost`, `127.0.0.1` or `file://` pages and aborts
any non-local sub-request, so it runs against the synthetic fixtures in
`tests/fixtures/` only.

Pass `--live` to `extract`/`fields`/`fill` to work a real application page for
human review: the localhost refusal lifts, the submit guard still gates every
action, file uploads are skipped (uploads stay manual), and `fill` saves a
full-page screenshot of the filled page (`<review>-filled.png`) before the
browser closes. Nothing is ever submitted in either mode.

```bash
python src/browser.py extract file://$PWD/tests/fixtures/greenhouse.html --out fields.json
python src/browser.py fields  file://$PWD/tests/fixtures/greenhouse.html   # print instead
python src/fill.py fields.json --profile answers/profile.json --no-model --out fill-plan.json
python src/browser.py fill file://$PWD/tests/fixtures/greenhouse.html \
  --plan fill-plan.json --out review.json
```

`fill` applies the plan, re-reads every field for the second pass, and
writes `review.json` with `stop_before_submit: true`. Every action goes
through `guard.assert_not_submit()`, so the run ends with the form filled
and never submitted. CI runs this end to end inside the image.

## The stop-before-submit guarantee

`src/guard.py` pattern-matches final-submission phrasing ("submit", "send
application", "confirm and apply", ...) and raises `SubmitBlocked` on any
action targeting such an element. The workflow ends with the form **filled
and not submitted**. A human reviews and clicks the button. This is enforced
in code, not just in the prompt.

## Layout

```
CLAUDE.md                     agent rules: karpathy guidelines + workflow tactics
.mcp.json                     Job Alerts MCP server for Claude Code
answers/profile.template.json copy to answers/profile.json (gitignored)
src/roles.py                  search the Herakraft Job Alerts API
src/mapping.py                form-label -> answer-key mapping, pure code
src/guard.py                  stop-before-submit enforcement
src/fill.py                   fill plan + OpenAI fallback + second-pass verify
```

## Form-label coverage

`src/label_table.py` holds 4,500+ real ATS form-label variants (Workday,
Greenhouse, Ashby, Lever, SmartRecruiters, Oracle/Taleo, iCIMS, Jibe) mapped
to profile keys. It is generated systematically: per-question base phrases
crossed with realistic phrasing patterns, all verified unique and mapping to
valid profile keys by `tests/test_label_table.py`. Seed phrases adapted from
the MIT-licensed [FormFilla](https://github.com/AhmadHassan-BTed/FormFilla)
dictionary (`src/shared/dictionary/rules.json`).

Resolution order on every form: (1) label table / code patterns - zero model
spend, (2) OpenAI fallback on the cheapest model for unseen labels only,
(3) human to-do for anything still unmapped. Each run prints a coverage
report (code vs model vs human) so model usage can be watched trending to
zero as the table grows.


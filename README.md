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

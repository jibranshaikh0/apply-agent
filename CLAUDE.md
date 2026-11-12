# CLAUDE.md

Rules for the agent building and running this job-application workflow. Two
parts: coding behavior (from Andrej Karpathy's LLM coding guidelines) and the
application-run rules (from "Four boring jobs I handed to AI agents, and the
exact setups that worked", Ree's Runbooks, Nov 2026).

## Part 1 - Coding behavior

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"

For multi-step tasks, state a brief plan:
```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

## Part 2 - Application workflow rules

These are the tactics that made high-volume application agents work. Follow
them on every run.

1. **Answers live in one file.** All applicant facts and answers are written
   once in `answers/profile.json` (copy the template, fill it in, never commit
   it). Never improvise applicant data. If a fact is missing, stop and ask the
   human - do not guess.

2. **Map form labels to answers in code, not in the model.**
   `src/mapping.py` resolves labels -> answer keys deterministically. The model
   is only a fallback classifier for labels code couldn't map, and it may only
   return an existing answer key - never new data. Different forms ask the same
   thing a hundred ways; the mapping table absorbs that, the model doesn't.

3. **Always run a second pass.** After filling, re-read every field from the
   page and compare it against the plan with `verify_filled()`. First passes
   make dumb errors: typing into dropdowns, values lost to overlays, stale
   fields. Fix and re-verify before presenting anything for review.

4. **Stop before submit.** Never click a final submit/apply button. Every
   click goes through `guard.assert_not_submit()`, which raises
   `SubmitBlocked` on submission phrasing. The pipeline ends with the form
   filled and ready; a human reviews and clicks submit. This is enforced in
   code - a prompt instruction alone is not acceptable.

5. **Arithmetic, lookups, sorting, and filtering happen in code.** Role
   search, dedup, grad-window and visa filtering are done by `src/roles.py`
   and plain Python. Don't ask the model to calculate or compare lists.

## Workflow

1. Search roles: `python src/roles.py --level new-grad --track swe --grad 2027`
   (or use the Job Alerts MCP server in `.mcp.json` - same catalog).
2. Shortlist with the human: they pick which roles to apply to.
3. For each application form: dump fields -> `src/fill.py` builds the fill
   plan -> fill via the browser -> `verify_filled()` second pass -> STOP.
4. Present the filled form to the human. They review and click submit.

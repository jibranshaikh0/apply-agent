#!/usr/bin/env python3
"""Application fill pipeline.

Flow (see CLAUDE.md, Part 2):
  1. The browser agent dumps the page's form fields as JSON:
     [{"id": "...", "label": "...", "type": "text|select|radio|file", "options": [...]}]
  2. build_fill_plan() maps labels -> profile values IN CODE (mapping.py).
     Only unmapped labels go to the OpenAI fallback, which may only return an
     existing profile key, never invent data.
  3. The agent fills fields, then runs the SECOND PASS: it re-reads every
     field's current value and calls verify_filled() to catch fill errors.
  4. guard.assert_not_submit() gates every click. The pipeline ends with the
     form filled and NOT submitted; a human reviews and clicks submit.

Usage:
    python src/fill.py fields.json --profile answers/profile.json --out fill-plan.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapping  # noqa: E402

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5-nano"


def load_profile(path: str) -> dict:
    with open(path) as f:
        profile = json.load(f)
    if profile.get("first_name") == "TODO":
        print("warning: answers/profile.json still has TODO placeholders", file=sys.stderr)
    return profile


def classify_with_openai(labels: list[str], known_keys: list[str]) -> dict[str, str | None]:
    """Fallback for labels code couldn't map. The model may ONLY return one of
    the known profile keys or null. It never sees or produces applicant data."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {label: None for label in labels}
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    prompt = (
        "Map each job-application form label to exactly one of these answer keys, "
        "or null if none fit. Reply with JSON only: {\"label\": \"key-or-null\"}.\n"
        f"Keys: {json.dumps(known_keys)}\nLabels: {json.dumps(labels)}"
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        OPENAI_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = json.load(resp)["choices"][0]["message"]["content"]
    raw = json.loads(content)
    # Validate: keep only mappings to real keys; anything else becomes unmapped.
    valid = set(known_keys)
    return {label: (raw.get(label) if raw.get(label) in valid else None) for label in labels}


def build_fill_plan(fields: list[dict], profile: dict, use_model: bool = True) -> dict:
    """Pass 1: resolve every field to a value. Code first, model fallback second."""
    # Leaf answers only: custom_answers is flattened in, not offered as a key.
    flat_profile = {k: v for k, v in profile.items()
                    if k != "custom_answers" and not isinstance(v, (dict, list))}
    flat_profile.update(profile.get("custom_answers", {}))
    # The model may choose from every canonical key, even one the profile
    # hasn't filled yet - that surfaces as missing_answers, a human to-do.
    known_keys = list(mapping.FIELD_ALIASES) + list(profile.get("custom_answers", {}))
    fills, unmapped, missing = [], [], []

    model_labels: list[str] = []
    model_fields: list[dict] = []
    for field in fields:
        key = mapping.map_label(field.get("label", ""))
        if key:
            value = flat_profile.get(key)
            if value and not str(value).startswith("TODO"):
                fills.append({"field_id": field["id"], "label": field["label"],
                              "key": key, "value": value, "source": "code"})
            else:
                missing.append({"field_id": field["id"], "label": field["label"], "key": key})
        else:
            model_labels.append(field.get("label", ""))
            model_fields.append(field)

    if use_model and model_labels:
        resolved = classify_with_openai(model_labels, known_keys)
        for field in model_fields:
            key = resolved.get(field.get("label", ""))
            value = flat_profile.get(key) if key else None
            if key and value and not str(value).startswith("TODO"):
                fills.append({"field_id": field["id"], "label": field["label"],
                              "key": key, "value": value, "source": "model"})
            elif key:
                missing.append({"field_id": field["id"], "label": field["label"], "key": key})
            else:
                unmapped.append({"field_id": field["id"], "label": field["label"]})
    else:
        unmapped.extend({"field_id": f["id"], "label": f.get("label", "")} for f in model_fields)

    return {"fills": fills, "unmapped": unmapped, "missing_answers": missing,
            "stop_before_submit": True}


def verify_filled(reread: dict[str, str], plan: dict) -> list[dict]:
    """Pass 2: compare what the page actually contains against the plan.

    reread: {field_id: current_value_on_page}. Returns mismatches to fix and
    re-verify before human review. Run this AFTER filling, always.
    """
    problems = []
    for fill in plan["fills"]:
        actual = (reread.get(fill["field_id"]) or "").strip()
        expected = str(fill["value"]).strip()
        if actual != expected:
            problems.append({"field_id": fill["field_id"], "label": fill["label"],
                             "expected": expected, "actual": actual})
    return problems


def main() -> int:
    p = argparse.ArgumentParser(description="Build a fill plan for an application form.")
    p.add_argument("fields", help="JSON file of form fields dumped from the page")
    p.add_argument("--profile", default="answers/profile.json")
    p.add_argument("--out", default=None)
    p.add_argument("--no-model", action="store_true", help="code mapping only")
    args = p.parse_args()

    with open(args.fields) as f:
        fields = json.load(f)
    plan = build_fill_plan(fields, load_profile(args.profile), use_model=not args.no_model)
    text = json.dumps(plan, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

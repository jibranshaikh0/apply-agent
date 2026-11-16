#!/usr/bin/env python3
"""Playwright browser layer (see CLAUDE.md, Part 2).

Subcommands:
  extract <url> --out fields.json   dump form fields in the shape fill.py consumes
  fields  <url>                     same, printed to stdout
  fill    <url> --plan fill-plan.json --out review.json
                                    apply the plan, run the second pass, write a review

Local synthetic pages only (localhost / 127.0.0.1 / file://); anything else is
refused, and non-local sub-requests are aborted. Every action is gated through
guard.assert_not_submit(). Nothing is ever submitted: the run ends with the
form filled and a human reviews it. Playwright is imported lazily so the repo
stays stdlib-only when this layer is unused.

Live mode (--live) deliberately lifts the localhost-only refusal so a real
application page can be filled for human review. The submit guard still gates
every action, file uploads are skipped (uploads stay manual), and the filled
page is screenshotted before the browser closes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fill  # noqa: E402
import guard  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1"}

# Runs in the page. Tags each control with data-af-id (radios share their
# group's id) so fill can find the same element extract described.
EXTRACT_JS = """() => {
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  const text = el => el ? clean(el.innerText || el.textContent) : '';
  const labelOf = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return text(l); }
    const wrap = el.closest('label'); if (wrap) return text(wrap);
    const by = el.getAttribute('aria-labelledby');
    if (by) return clean(by.split(' ').map(i => text(document.getElementById(i))).join(' '));
    return el.getAttribute('aria-label') || el.placeholder || '';
  };
  const nearby = el => {
    const fs = el.closest('fieldset'); const lg = fs && fs.querySelector('legend');
    if (lg) return text(lg);
    let p = el.previousElementSibling;
    if (p) return text(p);
    const parent = el.parentElement; return parent ? text(parent).slice(0, 120) : '';
  };
  const fields = [], groups = {};
  let n = 0;
  document.querySelectorAll('input, select, textarea').forEach(el => {
    const t = (el.type || el.tagName).toLowerCase();
    if (['submit', 'button', 'reset', 'image', 'hidden'].includes(t)) return;
    const base = el.id || el.name || `field-${n++}`;
    if (t === 'radio') {
      const key = el.name || base;
      let g = groups[key];
      if (!g) { g = groups[key] = {id: key, label: nearby(el), type: 'radio', options: []}; fields.push(g); }
      g.options.push(labelOf(el) || el.value);
      el.setAttribute('data-af-id', key);
      return;
    }
    el.setAttribute('data-af-id', base);
    const f = {id: base, label: labelOf(el) || nearby(el), type: t, options: []};
    if (el.tagName === 'SELECT') {
      f.type = 'select';
      f.options = [...el.options].filter(o => o.value !== '').map(o => clean(o.text));
    } else if (el.tagName === 'TEXTAREA' || !['file', 'checkbox'].includes(t)) f.type = 'text';
    fields.push(f);
  });
  return fields;
}"""


def check_local(url: str, live: bool = False) -> None:
    if live:
        return
    u = urlparse(url)
    if u.scheme == "file" or (u.scheme in ("http", "https") and u.hostname in LOCAL_HOSTS):
        return
    sys.exit(f"refused: {url!r} is not local (localhost/127.0.0.1/file:// only); pass --live to override")


def open_page(pw, url: str, live: bool = False):
    """Launch a headless page. Local mode restricts sub-requests to local ones."""
    check_local(url, live=live)
    browser = pw.chromium.launch()
    page = browser.new_page()
    if not live:
        page.route("**/*", lambda r: r.continue_() if _is_local(r.request.url) else r.abort())
    page.goto(url)
    if live:
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
    return browser, page


def _is_local(url: str) -> bool:
    u = urlparse(url)
    return u.scheme in ("file", "data", "about", "blob") or u.hostname in LOCAL_HOSTS


def extract_fields(page) -> list[dict]:
    return page.evaluate(EXTRACT_JS)


def _loc(page, field_id: str):
    return page.locator(f'[data-af-id="{field_id}"]')


def _label_text(page, el) -> str:
    """Text the guard should see for an element: label, value and visible text."""
    return " ".join(filter(None, [
        el.get_attribute("aria-label"), el.get_attribute("value"),
        el.get_attribute("name"), (el.inner_text() if el.evaluate("e => e.tagName") != "INPUT" else "")]))


def apply_fill(page, field: dict, value) -> None:
    """Fill one field; every action is gated through the submit guard first."""
    loc = _loc(page, field["id"])
    guard.assert_not_submit(f'{field["label"]} {_label_text(page, loc.first)}')
    kind, value = field["type"], str(value)
    if kind == "select":
        opts = loc.first.evaluate("e => [...e.options].map(o => o.text.trim())")
        match = next((o for o in opts if o.lower() == value.lower()), value)
        loc.select_option(label=match)
    elif kind == "radio":
        for i in range(loc.count()):
            radio = loc.nth(i)
            text = radio.evaluate("e => (e.labels && e.labels[0] ? e.labels[0].innerText : e.value)").strip()
            if value.lower() in (text.lower(), (radio.get_attribute("value") or "").lower()):
                guard.assert_not_submit(text)
                radio.check()
                return
        raise ValueError(f"no radio option {value!r} for {field['label']!r}")
    elif kind == "checkbox":
        loc.set_checked(value.lower() in ("yes", "true", "1"))
    elif kind == "file":
        loc.set_input_files(value)
    else:
        loc.fill(value)


def reread(page, fields: list[dict]) -> dict[str, str]:
    """Second pass input: current value of every field as the page holds it."""
    out = {}
    for f in fields:
        loc = _loc(page, f["id"])
        if f["type"] == "select":
            out[f["id"]] = loc.evaluate("e => e.selectedIndex < 0 ? '' : e.options[e.selectedIndex].text.trim()")
        elif f["type"] == "radio":
            out[f["id"]] = loc.evaluate_all(
                "els => { const r = els.find(e => e.checked); "
                "return r ? (r.labels && r.labels[0] ? r.labels[0].innerText.trim() : r.value) : ''; }")
        elif f["type"] == "checkbox":
            out[f["id"]] = "yes" if loc.is_checked() else "no"
        elif f["type"] == "file":
            out[f["id"]] = loc.evaluate("e => e.files.length ? e.files[0].name : ''")
        else:
            out[f["id"]] = loc.input_value()
    return out


def cmd_extract(args) -> int:
    check_local(args.url, live=getattr(args, "live", False))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser, page = open_page(pw, args.url, live=getattr(args, "live", False))
        fields = extract_fields(page)
        browser.close()
    text = json.dumps(fields, indent=2)
    if getattr(args, "out", None):
        with open(args.out, "w") as f:
            f.write(text)
    else:
        print(text)
    return 0


def cmd_fill(args) -> int:
    live = getattr(args, "live", False)
    check_local(args.url, live=live)
    from playwright.sync_api import sync_playwright
    with open(args.plan) as f:
        plan = json.load(f)
    applied, errors, skipped_uploads = [], [], []
    with sync_playwright() as pw:
        browser, page = open_page(pw, args.url, live=live)
        fields = {f["id"]: f for f in extract_fields(page)}
        for item in plan["fills"]:
            field = fields.get(item["field_id"])
            if field is None:
                errors.append({"field_id": item["field_id"], "error": "field not on page"})
                continue
            if live and field["type"] == "file":
                skipped_uploads.append({"field_id": item["field_id"], "label": item.get("label"),
                                        "reason": "uploads stay manual in live mode"})
                continue
            try:
                apply_fill(page, field, item["value"])
                applied.append({k: item[k] for k in ("field_id", "label", "value", "source") if k in item})
            except guard.SubmitBlocked:
                raise
            except Exception as e:  # leave it for the second pass / human
                errors.append({"field_id": item["field_id"], "error": str(e)})
        # Second pass: re-read what the page holds and compare with the plan.
        # File inputs only expose the file name, so compare against the basename.
        checked = {"fills": [
            {**i, "value": os.path.basename(str(i["value"])) if fields.get(i["field_id"], {}).get("type") == "file"
             else i["value"]}
            for i in plan["fills"] if i["field_id"] in fields]}
        now = reread(page, list(fields.values()))
        # Choice controls are matched case-insensitively when filling ("yes" -> "Yes"),
        # so compare them the same way instead of reporting a false mismatch.
        for i in checked["fills"]:
            if fields[i["field_id"]]["type"] in ("select", "radio") and \
                    now[i["field_id"]].lower() == str(i["value"]).strip().lower():
                now[i["field_id"]] = str(i["value"]).strip()
        mismatches = fill.verify_filled(now, checked)
        screenshot = None
        if live:
            screenshot = os.path.splitext(args.out)[0] + "-filled.png"
            page.screenshot(path=screenshot, full_page=True)
        browser.close()
    review = {"url": args.url, "fills_applied": applied, "errors": errors,
              "coverage": plan.get("coverage"),
              "mismatches": mismatches, "unmapped": plan.get("unmapped", []),
              "missing_answers": plan.get("missing_answers", []),
              "skipped_uploads": skipped_uploads,
              "screenshot": screenshot,
              "stop_before_submit": True}
    with open(args.out, "w") as f:
        json.dump(review, f, indent=2)
    print(f"filled {len(applied)}, {len(errors)} errors, {len(mismatches)} mismatches; "
          f"NOT submitted - review {args.out}", file=sys.stderr)
    return 1 if errors or mismatches else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Browser layer: extract fields, fill a plan, never submit.")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="write form fields JSON for fill.py")
    e.add_argument("url")
    e.add_argument("--out", required=True)
    e.add_argument("--live", action="store_true",
                   help="allow a live (non-local) page; guard still blocks submit actions")
    e.set_defaults(func=cmd_extract)
    s = sub.add_parser("fields", help="print form fields JSON to stdout")
    s.add_argument("url")
    s.add_argument("--live", action="store_true",
                   help="allow a live (non-local) page; guard still blocks submit actions")
    s.set_defaults(func=cmd_extract)
    f = sub.add_parser("fill", help="apply a fill plan, run the second pass, write a review")
    f.add_argument("url")
    f.add_argument("--plan", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--live", action="store_true",
                   help="allow a live (non-local) page; guard still blocks submit actions, "
                        "file uploads are skipped (manual), filled page is screenshotted")
    f.set_defaults(func=cmd_fill)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

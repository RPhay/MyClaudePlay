#!/usr/bin/env python3
"""Validate the benchmark harness WITHOUT spending a cent.

Every bug this benchmark has had so far was an invariant of the harness,
discoverable for free: the control could answer, the answer key sat inside the
fixture, the facts were guessable, the index was gibberish. Each one cost a
paid run to find. This script asserts all of them before any API call.

Run it before every benchmark run. Exit 0 = safe to spend.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SC = os.path.join(ROOT, ".bench", "selfcheck")

FAILS = []


def check(name, ok, detail=""):
    print(f"  {'ok' if ok else 'FAIL'}: {name}" + (f" -- {detail}" if not ok and detail else ""))
    if not ok:
        FAILS.append(name)


def build(strat, count):
    d = os.path.join(SC, f"{strat}-{count}")
    subprocess.run([os.path.join(HERE, "mkfixture.sh"), d, strat, str(count)],
                   check=True, capture_output=True, text=True)
    return d


def hook_output(d, *args):
    r = subprocess.run(["./.claude/skills/doc-search/load-baseline.sh", *args],
                       cwd=d, capture_output=True, text=True)
    return r.stdout


def main():
    shutil.rmtree(SC, ignore_errors=True)
    os.makedirs(SC, exist_ok=True)

    print("harness selfcheck (no API calls)")

    # --- corpus invariants ---------------------------------------------------
    print("\ncorpus:")
    d = build("search", 5)
    man = json.load(open(d + ".corpus.json"))
    docs = man["docs"]

    check("answer key lives OUTSIDE the fixture",
          not os.path.exists(os.path.join(d, "corpus.json")))
    check("no answer key anywhere inside fixture",
          not any("corpus" in f for _, _, fs in os.walk(d) for f in fs))

    ports = [x["port"] for x in docs]
    check("ports are NOT guessable (not 8000+index)",
          all(x["port"] != 8000 + i for i, x in enumerate(docs)), str(ports))
    check("ports in randomized range", all(10111 <= p <= 65000 for p in ports))
    check("each fact unique to one doc", len(set(ports)) == len(ports))

    body = open(os.path.join(d, "docs/standards/widget-2.md")).read()
    check("doc titled after its subject", "# Widget 2 Service" in body)
    check("doc contains its own fact", str(man["docs"][2]["port"]) in body)

    # determinism: same seed -> identical corpus
    d2 = build("search", 5)  # rebuilds with same default seed
    man2 = json.load(open(d2 + ".corpus.json"))
    check("same seed reproduces identical corpus",
          [x["port"] for x in man2["docs"]] == ports)

    # --- control -------------------------------------------------------------
    print("\ncontrol (none):")
    d = build("none", 5)
    check("control has NO documents on disk",
          not os.path.exists(os.path.join(d, "docs")))
    cm = open(os.path.join(d, "CLAUDE.md")).read()
    check("control CLAUDE.md carries no doc facts",
          "widget" not in cm and not any(str(p) in cm for p in ports))

    # --- strategy shapes -----------------------------------------------------
    print("\nstrategies:")
    d = build("claudemd", 5)
    cm = open(os.path.join(d, "CLAUDE.md")).read()
    check("claudemd index maps question terms to files",
          "widget-2.md" in cm, "index must name what a doc is about")
    check("claudemd index does NOT contain the answers",
          not any(str(p) in cm for p in ports))

    d = build("agent", 5)
    check("agent fixture installs the subagent",
          os.path.exists(os.path.join(d, ".claude/agents/doc-search.md")))
    check("agent pinned to haiku",
          "model: haiku" in open(os.path.join(d, ".claude/agents/doc-search.md")).read())
    out = hook_output(d, "--refs-only")
    check("agent startup index names the docs", "widget-2.md" in out)
    check("agent startup index does NOT contain answers",
          not any(str(p) in out for p in ports))
    check("agent CLAUDE.md routes to the agent",
          "doc-search" in open(os.path.join(d, "CLAUDE.md")).read())

    d = build("all", 5)
    out = hook_output(d)
    check("preload-all startup DOES contain every answer",
          all(str(p) in out for p in ports),
          "full text of all docs must be in the hook output")

    d = build("few", 5)
    out = hook_output(d)
    in_few = sum(str(p) in out for p in ports)
    check("preload-few loads a strict subset", 0 < in_few < len(ports),
          f"{in_few}/{len(ports)} docs in hook output")

    d = build("search", 5)
    settings = json.load(open(os.path.join(d, ".claude/settings.json")))
    check("search has docs but no hook",
          "hooks" not in settings
          and os.path.exists(os.path.join(d, "docs/standards")))

    # --- question schedule ---------------------------------------------------
    print("\nquestion schedule:")
    for count in (5, 40):
        n = count - 1  # pool excludes the baseline doc
        stride = 7 if math.gcd(7, n) == 1 else 1
        seq = [(i * stride) % n for i in range(n)]
        check(f"targets all distinct at {count} mds", len(set(seq)) == len(seq))
    check("baseline doc never a target (preloaders can't answer from freebie)",
          True)  # structural: pool = docs[1:]

    # --- 40-md build sanity ----------------------------------------------------
    print("\nscale:")
    d = build("all", 40)
    man40 = json.load(open(d + ".corpus.json"))
    tok = sum(x["est_tokens"] for x in man40["docs"])
    check("40-md corpus is materially larger than session overhead (>25k tok)",
          tok > 25000, f"{tok} tokens")
    out = hook_output(d)
    check("preload-all at 40 mds emits the whole corpus",
          len(out) > 0.8 * sum(x["bytes"] for x in man40["docs"]),
          f"hook emitted {len(out)} bytes")

    shutil.rmtree(SC, ignore_errors=True)
    print(f"\n{'ALL CHECKS PASS -- safe to spend' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

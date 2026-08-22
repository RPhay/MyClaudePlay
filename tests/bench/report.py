#!/usr/bin/env python3
"""Aggregate the loading-strategy benchmark.

Two questions, in this order:

  1. What ends up sitting in the session?
  2. What does that cost, per turn and over short vs long sessions?

Costs are the CLI's own `total_cost_usd`. Nothing here is modelled.

  report.py .bench/matrix.jsonl
"""

import json
import statistics as st
import sys

NAME = {
    "none":     "no mds loaded",
    "search":   "claude searches for them",
    "claudemd": "loaded by default via CLAUDE.md",
    "few":      "loading a few",
    "all":      "loading them all",
    "agent":    "doc-search skill+agent  <-- OURS",
}
ORDER = ["none", "search", "claudemd", "few", "all", "agent"]
W = 36


def mean(v):
    return st.mean(v) if v else 0.0


def sd(v):
    return st.stdev(v) if len(v) > 1 else 0.0


def load(paths):
    rows = []
    for p in paths:
        for line in open(p):
            line = line.strip()
            if line:
                r = json.loads(line)
                if "error" not in r:
                    rows.append(r)
    return rows


def cols(docs, turns):
    return [(d, t) for d in docs for t in turns]


def collabel(d, t, turns):
    """Columns in plain terms: no jargon, just corpus size and chat length."""
    kind = "short chat" if t == min(turns) else "long chat"
    return f"{d} mds / {kind}"


def md_table(rows, docs, turns, value, fmt, title, note="", pct=True):
    """Emit a markdown table. Each cell also carries its % difference against
    the 'no mds loaded' baseline for the same column, so the cost of a strategy
    is legible without doing arithmetic across rows."""
    print(f"\n**{title}**")
    if note:
        print(f"\n_{note}_")
    cs = cols(docs, turns)

    base = {}
    for d, t in cs:
        b = [value(r) for r in rows if r["strategy"] == "none"
             and r["docs"] == d and r["turns"] == t]
        base[(d, t)] = mean(b) if b else None

    print()
    print("| strategy | " + " | ".join(collabel(d, t, turns) for d, t in cs) + " |")
    print("|---|" + "---|" * len(cs))
    for s in ORDER:
        sr = [r for r in rows if r["strategy"] == s]
        if not sr:
            continue
        cells = []
        for d, t in cs:
            c = [value(r) for r in sr if r["docs"] == d and r["turns"] == t]
            if not c:
                cells.append("—")
                continue
            v = mean(c)
            txt = fmt(v)
            b = base.get((d, t))
            if pct and b:
                delta = (v - b) / b * 100
                txt += f" (**{delta:+.0f}%**)" if s != "none" else " (base)"
            cells.append(txt)
        print(f"| {NAME[s]} | " + " | ".join(cells) + " |")


table = md_table


def main(paths):
    rows = load(paths)
    if not rows:
        print("no successful rows")
        return 1

    docs = sorted({r["docs"] for r in rows})
    turns = sorted({r["turns"] for r in rows})
    models = sorted({r["model"] for r in rows})
    ctok = {d: [r["corpus_tokens"] for r in rows if r["docs"] == d][0]
            for d in docs}

    print(f"{len(rows)} sessions | model: {', '.join(models)} | "
          f"repeats: {max(r['rep'] for r in rows)+1}")
    print("corpus:  " + " | ".join(f"{d} mds = ~{ctok[d]:,} tokens on disk"
                                   for d in docs))
    print("chat length: short = {} messages, long = {} messages"
          .format(min(turns), max(turns)))
    

    for m in models:
        mr = [r for r in rows if r["model"] == m]
        if len(models) > 1:
            print(f"\n{'='*80}\nMAIN SESSION MODEL: {m}\n{'='*80}")

        table(mr, docs, turns, lambda r: r["resident_tokens"],
              lambda v: f"{v:,.0f}",
              "1. TOKENS SITTING IN THE SESSION",
              "re-sent on every message you send: system prompt, tools, and whatever md text landed")

        base_ctx = {}
        for d in docs:
            for t in turns:
                c = [r["resident_tokens"] for r in mr
                     if r["strategy"] == "none" and r["docs"] == d
                     and r["turns"] == t]
                base_ctx[(d, t)] = mean(c) if c else 0

        print("\n**2. OF THAT, HOW MUCH IS MARKDOWN**")
        print("\n_resident tokens minus the empty-session baseline_\n")
        cs = cols(docs, turns)
        print("| strategy | " + " | ".join(collabel(d, t, turns) for d, t in cs) + " |")
        print("|---|" + "---|" * len(cs))
        for s in ORDER:
            sr = [r for r in mr if r["strategy"] == s]
            if not sr:
                continue
            cells = []
            for d, t in cs:
                c = [r["resident_tokens"] for r in sr
                     if r["docs"] == d and r["turns"] == t]
                cells.append(f"{mean(c) - base_ctx[(d, t)]:+,.0f}" if c else "—")
            print(f"| {NAME[s]} | " + " | ".join(cells) + " |")

        table(mr, docs, turns,
              lambda r: r.get("cost_per_msg_end", r["cost_per_turn"]),
              lambda v: f"${v:.4f}",
              "3. $ PER MESSAGE AT END OF CHAT",
              "the bleed after everything has accumulated: every further message costs this")

        table(mr, docs, turns, lambda r: r["cost"], lambda v: f"${v:.4f}",
              "4. TOTAL SESSION COST")

        table(mr, docs, turns,
              lambda r: r.get("accuracy", 1.0 if r["correct"] else 0.0),
              lambda v: f"{v*100:.0f}%",
              "5. QUESTIONS ANSWERED CORRECTLY",
              "several doc questions per chat; 'no mds loaded' cannot answer by design",
              pct=False)

        print("\n**6. SPREAD (sd as % of mean) — is any ordering above real?**\n")
        cs = cols(docs, turns)
        print("| strategy | " + " | ".join(collabel(d, t, turns) for d, t in cs) + " |")
        print("|---|" + "---|" * len(cs))
        for s in ORDER:
            sr = [r for r in mr if r["strategy"] == s]
            if not sr:
                continue
            cells = []
            for d, t in cs:
                c = [r["cost"] for r in sr
                     if r["docs"] == d and r["turns"] == t]
                cells.append(f"{sd(c)/mean(c)*100:.0f}%"
                             if len(c) > 1 and mean(c) else "—")
            print(f"| {NAME[s]} | " + " | ".join(cells) + " |")

        # ---- verdict --------------------------------------------------
        print("\n" + "=" * 80)
        print("VERDICT: is doc-search (skill+agent) better than every alternative?")
        print("=" * 80)
        rivals = [x for x in ORDER if x not in ("agent", "none")]
        wins = losses = 0
        for d in docs:
            for t in turns:
                ours = [r for r in mr if r["strategy"] == "agent"
                        and r["docs"] == d and r["turns"] == t]
                if not ours:
                    continue
                oc = mean([r["cost"] for r in ours])
                oa = mean([r.get("accuracy", 0.0) for r in ours])
                print(f"\n  {collabel(d, t, turns)}   "
                      f"ours: ${oc:.4f}, {oa*100:.0f}% correct")
                beaten = []
                for s_ in rivals:
                    rr = [r for r in mr if r["strategy"] == s_
                          and r["docs"] == d and r["turns"] == t]
                    if not rr:
                        continue
                    rc = mean([r["cost"] for r in rr])
                    ra = mean([r.get("accuracy", 0.0) for r in rr])
                    lost = rc < oc and ra >= oa
                    if lost:
                        beaten.append(f"{NAME[s_]} (${rc:.4f})")
                    print(f"      vs {NAME[s_]:<{W}} ${rc:.4f} {ra*100:>4.0f}%  "
                          f"{'BEATS US' if lost else 'we win'}")
                if beaten:
                    losses += 1
                    print(f"    -> BEATEN BY: {'; '.join(beaten)}")
                else:
                    wins += 1
                    print("    -> BEST IN THIS CELL")
        tot = wins + losses
        if not tot:
            print("\n  No doc-search rows yet - no verdict.")
            continue
        print(f"\n  doc-search is best in {wins} of {tot} cells.")
        if losses == 0:
            print("  => KEEP IT.")
        elif wins == 0:
            print("  => THROW IT AWAY. Something simpler beats it everywhere.")
        else:
            print("  => CONDITIONAL - it only pays in some regimes. See cells above.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or [".bench/matrix.jsonl"]))

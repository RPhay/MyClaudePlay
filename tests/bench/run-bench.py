#!/usr/bin/env python3
"""Run the doc-search benchmark: real headless Claude Code sessions, real numbers.

Measures each architecture variant over a MULTI-TURN session, because the whole
delegate-by-default argument rests on carrying cost -- what a document costs on
every turn after the one that read it. A single-shot run cannot see that.

Turn 1 asks a question only one document can answer. Turns 2..N are trivial
filler that use no tools, so their cost is almost entirely the re-sent context.

Cost comes from the CLI's own `total_cost_usd`, so nothing here depends on my
assumptions about cache pricing or input/output split.

  run-bench.py --strategies none,search,claudemd,few,all,agent \
               --models haiku --docs 5,40 --turns 3,15 --repeats 2
"""

import argparse
import math
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BENCH = os.path.join(ROOT, ".bench")

FILLER = "Reply with exactly: ack"


def run_claude(cwd, prompt, model, resume=None):
    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--model", model, "--dangerously-skip-permissions"]
    if resume:
        cmd += ["--resume", resume]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    wall = time.time() - t0
    if p.returncode != 0 or not p.stdout.strip():
        return {"error": (p.stderr or "no stdout")[:400], "wall": wall}
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"error": "unparseable json: " + p.stdout[:200], "wall": wall}
    u = d.get("usage", {}) or {}
    return {
        "session_id": d.get("session_id"),
        "result": d.get("result", "") or "",
        "cost": d.get("total_cost_usd") or 0.0,
        "input": u.get("input_tokens", 0) or 0,
        "output": u.get("output_tokens", 0) or 0,
        "cache_create": u.get("cache_creation_input_tokens", 0) or 0,
        "cache_read": u.get("cache_read_input_tokens", 0) or 0,
        "num_turns": d.get("num_turns", 0),
        "is_error": bool(d.get("is_error")),
        "wall": wall,
    }


def one_session(fixture, model, targets, turns, ask_every):
    """One multi-turn session that keeps asking about NEW documents.

    This is the point of the whole benchmark. A session does not read one
    document and stop -- it keeps asking, and with the read-it-yourself
    strategies every answer drags another full document into the context and
    leaves it there. Every later message re-sends all of them. Filler-only
    turns hide that completely, which is what an earlier version of this
    harness did.
    """
    turn_rows, asked, correct = [], [], []
    sid = None
    qi = 0

    for turn in range(turns):
        is_q = (turn % ask_every == 0) and qi < len(targets)
        if is_q:
            tg = targets[qi]
            prompt = (f"What port does the {tg['widget']} service listen on, "
                      f"and which team owns it? Answer in one short sentence.")
        else:
            prompt = FILLER

        r = run_claude(fixture, prompt, model, resume=sid)
        if "error" in r:
            if not turn_rows:
                return {"error": r["error"]}
            break
        turn_rows.append(r)
        sid = r.get("session_id") or sid

        if is_q:
            asked.append(tg["widget"])
            correct.append(str(tg["port"]) in r["result"])
            qi += 1

    tot = {k: sum(t.get(k, 0) for t in turn_rows)
           for k in ("cost", "input", "output", "cache_create", "cache_read",
                     "num_turns", "wall")}
    tot["turns_completed"] = len(turn_rows)
    tot["questions_asked"] = len(asked)
    tot["questions_right"] = sum(correct)
    tot["correct"] = (all(correct) if correct else False)
    tot["accuracy"] = (sum(correct) / len(correct)) if correct else 0.0

    ctx = [t["cache_read"] + t["cache_create"] + t["input"] for t in turn_rows]
    # Non-question messages show the resident session cleanly: one iteration,
    # nothing new added. Question messages inflate it with tool-call rounds.
    plain = [(i, c) for i, c in enumerate(ctx) if i % ask_every != 0]
    tot["ctx_first"] = plain[0][1] if plain else ctx[0]
    tot["ctx_last"] = plain[-1][1] if plain else ctx[-1]
    tot["ctx_growth"] = tot["ctx_last"] - tot["ctx_first"]
    tot["resident_tokens"] = tot["ctx_last"]

    plain_costs = [turn_rows[i]["cost"] for i, _ in plain]
    tot["cost_per_turn"] = (sum(plain_costs) / len(plain_costs)
                            if plain_costs else turn_rows[0]["cost"])
    tot["cost_per_msg_end"] = plain_costs[-1] if plain_costs else 0.0
    tot["q1_cost"] = turn_rows[0]["cost"]
    tot["carry_cost"] = tot["cost"] - turn_rows[0]["cost"]
    tot["answer"] = turn_rows[0]["result"][:180]
    tot["turn_detail"] = [{"i": i, "q": (i % ask_every == 0),
                           "cost": round(t["cost"], 6), "ctx": c}
                          for i, (t, c) in enumerate(zip(turn_rows, ctx))]
    return tot


def mean_int(v):
    return int(sum(v) / len(v)) if v else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies", default="none,search,claudemd,few,all,agent")
    ap.add_argument("--models", default="haiku")
    ap.add_argument("--docs", default="5,40",
                    help="comma-separated corpus sizes (small,large)")
    ap.add_argument("--turns", default="3,15",
                    help="comma-separated session lengths (short,long context)")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1729)
    ap.add_argument("--size", default="mixed")
    ap.add_argument("--out", default=os.path.join(BENCH, "matrix.jsonl"))
    ap.add_argument("--ask-every", type=int, default=2,
                    help="ask a NEW doc question every N messages; the rest "
                         "are filler. This is what makes documents accumulate.")
    ap.add_argument("--append", action="store_true")
    a = ap.parse_args()

    strategies = a.strategies.split(",")
    models = a.models.split(",")
    doc_counts = [int(x) for x in a.docs.split(",")]
    turn_counts = [int(x) for x in a.turns.split(",")]
    os.makedirs(BENCH, exist_ok=True)

    total = (len(strategies) * len(models) * len(doc_counts)
             * len(turn_counts) * a.repeats)
    print(f"{total} sessions | strategies={strategies} | docs={doc_counts} "
          f"| turns={turn_counts} | models={models} | repeats={a.repeats}",
          flush=True)

    done = 0
    spent = 0.0
    with open(a.out, "a" if a.append else "w") as fh:
        for ndocs in doc_counts:
            for strat in strategies:
                fixture = os.path.join(BENCH, f"fx-{strat}-{ndocs}")
                subprocess.run([os.path.join(HERE, "mkfixture.sh"), fixture,
                                strat, str(ndocs), str(a.seed), a.size],
                               check=True, capture_output=True, text=True)
                corpus = json.load(open(fixture + ".corpus.json"))
                # Target a doc away from index 0, so the strategies that
                # preload a subset cannot answer from what they already hold.
                # Distinct documents only, deterministically scrambled.
                # Every question must pull in a NEW document; if the corpus is
                # small the session simply runs out of questions and the rest
                # of the chat is filler. Never re-ask -- a repeated question
                # is free for preload/search and would rig the small-corpus
                # cells in their favour.
                pool = corpus["docs"][1:] or corpus["docs"]
                n = len(pool)
                stride = 7 if math.gcd(7, n) == 1 else 1
                targets = [pool[(i * stride) % n] for i in range(n)]
                corpus_tokens = sum(d["est_tokens"] for d in corpus["docs"])

                for nturns in turn_counts:
                    for model in models:
                        for rep in range(a.repeats):
                            done += 1
                            print(f"  [{done}/{total}] {strat:<9} docs={ndocs:<3} "
                                  f"turns={nturns:<3} {model} r{rep+1} ... ",
                                  end="", flush=True)
                            row = one_session(fixture, model, targets,
                                              nturns, a.ask_every)
                            row.update(strategy=strat, model=model, rep=rep,
                                       docs=ndocs, turns=nturns,
                                       corpus_tokens=corpus_tokens,
                                       ask_every=a.ask_every)
                            fh.write(json.dumps(row) + "\n")
                            fh.flush()
                            if "error" in row:
                                print("ERROR:", row["error"][:80])
                            else:
                                spent += row["cost"]
                                print(f"${row['cost']:.4f}  "
                                      f"{row['questions_right']}/{row['questions_asked']}q  "
                                      f"+{row['ctx_growth']:,}tok  "
                                      f"{row['wall']:.0f}s   [spent ${spent:.2f}]")
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())

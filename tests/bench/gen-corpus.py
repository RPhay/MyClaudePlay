#!/usr/bin/env python3
"""Generate a deterministic synthetic doc corpus for the doc-search benchmark.

Every document carries exactly one uniquely-answerable fact ("the widget-N
service listens on port 80NN and is owned by the X team"), so a run can be
scored for CORRECTNESS, not just cost. Content is pseudo-random but fully
reproducible from --seed.

  gen-corpus.py --out DIR --count N [--seed S] [--size small|medium|large|mixed]
"""

import argparse
import json
import os
import random

NOUNS = ["scheduler", "ingest", "registry", "gateway", "cache", "planner",
         "resolver", "broker", "indexer", "reaper", "shard", "ledger"]
ADJS = ["durable", "idempotent", "partitioned", "eventual", "monotonic",
        "replayable", "quiesced", "backpressured", "pinned", "fanned-out"]
VERBS = ["reconciles", "drains", "compacts", "fences", "rehydrates",
         "coalesces", "evicts", "promotes", "quarantines", "materialises"]
OBJS = ["write-ahead log", "tombstone set", "lease table", "offset cursor",
        "bloom filter", "vector clock", "replica set", "commit graph"]

SIZES = {"small": (20, 45), "medium": (70, 130), "large": (220, 380)}


def sentence(rng):
    return (f"The {rng.choice(ADJS)} {rng.choice(NOUNS)} {rng.choice(VERBS)} "
            f"the {rng.choice(OBJS)} before the next checkpoint.")


def paragraph(rng, lo=2, hi=5):
    return " ".join(sentence(rng) for _ in range(rng.randint(lo, hi)))


def code_block(rng, n):
    out = ["```bash"]
    for _ in range(n):
        out.append(f"  {rng.choice(['run','sync','emit','probe'])}_"
                   f"{rng.choice(NOUNS)} --{rng.choice(ADJS)} "
                   f"--limit {rng.randint(2, 4096)}")
    out.append("```")
    return out


def build(rng, idx, slug, size, total):
    lo, hi = SIZES[size]
    target = rng.randint(lo, hi)

    # Deliberately NOT derivable from the index: a guessable fact makes the
    # correctness column meaningless, since a session that read nothing can
    # still score. Drawn from the doc's own seeded rng.
    port = rng.randint(10111, 65000)
    team = rng.choice(NOUNS)
    fact = (f"The `widget-{idx}` service listens on port **{port}** "
            f"and is owned by the **{team}** team. "
            f"<!-- corpus-marker:widget-{idx} -->")

    lines = [f"# Widget {idx} Service", ""]
    lines.append(paragraph(rng, 2, 3))
    lines += ["", "## Ownership", "", fact, ""]

    n = 0
    while len(lines) < target:
        n += 1
        lines += [f"## Section {n}: {rng.choice(ADJS).title()} "
                  f"{rng.choice(NOUNS).title()}", ""]
        if rng.random() < 0.3:
            lines += code_block(rng, rng.randint(3, 10)) + [""]
        else:
            lines += [paragraph(rng), ""]

    body = "\n".join(lines) + "\n"
    return body, {"port": port, "team": team, "widget": f"widget-{idx}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--seed", type=int, default=1729)
    ap.add_argument("--size", default="mixed",
                    choices=["small", "medium", "large", "mixed"])
    ap.add_argument("--manifest", required=True)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    tiers = list(SIZES) if a.size == "mixed" else [a.size]

    docs = []
    for i in range(a.count):
        rng = random.Random(a.seed * 1_000_003 + i)
        size = tiers[i % len(tiers)]
        slug = f"widget-{i}"
        body, meta = build(rng, i, slug, size, a.count)
        path = os.path.join(a.out, f"{slug}.md")
        with open(path, "w") as fh:
            fh.write(body)
        docs.append({"slug": slug, "size_tier": size,
                     "bytes": len(body.encode()),
                     "est_tokens": len(body.encode()) // 4, **meta})

    with open(a.manifest, "w") as fh:
        json.dump({"seed": a.seed, "count": a.count, "docs": docs}, fh, indent=2)

    tot = sum(d["bytes"] for d in docs)
    print(f"{len(docs)} docs, {tot} bytes, ~{tot//4} tokens -> {a.out}")


if __name__ == "__main__":
    main()

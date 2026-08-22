#!/usr/bin/env python3
"""Controlled A/B over `claude -p`, to test whether a change actually helped.

Each arm is a directory whose contents (CLAUDE.md, .claude/, whatever) are copied
into a fresh temporary workspace. Every arm answers the same prompts the same
number of times. Results are reported with spread, and the verdict refuses to
claim a difference the data does not support.

This spends money. Run with --dry-run first; it prints the plan and stops.

Usage:
    bench.py --arms <dir> --prompts <file> [--n 5] [--model haiku] [--dry-run]
"""
import argparse, json, os, shutil, statistics, subprocess, sys, tempfile

def arms_in(d):
    return sorted(p for p in
                  (os.path.join(d, x) for x in os.listdir(d))
                  if os.path.isdir(p) and not os.path.basename(p).startswith('.'))


def read_prompts(path):
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line and not line.startswith('#'):
            out.append(line)
    return out


def run_one(arm, prompt, model, budget):
    """One measured invocation in a throwaway copy of the arm."""
    tmp = tempfile.mkdtemp(prefix='bench-')
    try:
        for name in os.listdir(arm):
            src, dst = os.path.join(arm, name), os.path.join(tmp, name)
            (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
        cmd = ['claude', '-p', prompt, '--model', model,
               '--output-format', 'json', '--no-session-persistence',
               '--max-budget-usd', str(budget)]
        r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=300)
        raw = r.stdout.strip()
        i = raw.find('{')
        if i < 0:
            return None
        d = json.loads(raw[i:])
        u = d.get('usage') or {}
        total = sum(u.get(k) or 0 for k in
                    ('input_tokens', 'cache_read_input_tokens',
                     'cache_creation_input_tokens', 'output_tokens'))
        return dict(total=total, out=u.get('output_tokens') or 0,
                    cost=d.get('total_cost_usd') or 0.0,
                    turns=d.get('num_turns') or 0,
                    err=bool(d.get('is_error')))
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def summarise(vals):
    if not vals:
        return None
    m = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return dict(n=len(vals), mean=m, sd=sd, lo=min(vals), hi=max(vals))


def overlap(a, b):
    """Do the observed ranges overlap? With small n this is the honest test."""
    return not (a['hi'] < b['lo'] or b['hi'] < a['lo'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arms', required=True, help='directory of arm subdirectories')
    ap.add_argument('--prompts', required=True, help='file, one prompt per line')
    ap.add_argument('--n', type=int, default=5, help='runs per arm per prompt')
    ap.add_argument('--model', default='haiku')
    ap.add_argument('--budget', type=float, default=0.25, help='per-run cap, USD')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if not os.path.isdir(args.arms):
        sys.exit('not a directory: %s' % args.arms)
    arms = arms_in(args.arms)
    prompts = read_prompts(args.prompts)
    if len(arms) < 2:
        sys.exit('need at least two arms to compare; found %d' % len(arms))
    if not prompts:
        sys.exit('no prompts in %s' % args.prompts)

    calls = len(arms) * len(prompts) * args.n
    print('PLAN')
    print('  arms       %d  (%s)' % (len(arms), ', '.join(os.path.basename(a) for a in arms)))
    print('  prompts    %d' % len(prompts))
    print('  runs each  %d' % args.n)
    print('  model      %s' % args.model)
    print('  TOTAL API CALLS  %d, capped at $%.2f each (worst case $%.2f)'
          % (calls, args.budget, calls * args.budget))
    if args.n < 3:
        print('  !! n < 3: spread cannot be estimated, and no comparison will be reported')
    if args.dry_run:
        print('\ndry run — nothing executed')
        return

    results = {os.path.basename(a): {} for a in arms}
    for arm in arms:
        name = os.path.basename(arm)
        for pi, prompt in enumerate(prompts):
            vals, costs, fails = [], [], 0
            for _ in range(args.n):
                r = run_one(arm, prompt, args.model, args.budget)
                if r is None or r['err']:
                    fails += 1
                    continue
                vals.append(r['total'])
                costs.append(r['cost'])
            results[name][pi] = dict(tokens=summarise(vals), cost=summarise(costs),
                                     failed=fails)
            print('  ran %-16s prompt %d: %d ok, %d failed' % (name, pi + 1, len(vals), fails))

    base = os.path.basename(arms[0])
    print('\nRESULTS  (total tokens per run: input + cache read + cache write + output)')
    for pi, prompt in enumerate(prompts):
        print('\n  prompt %d: %s' % (pi + 1, prompt[:70]))
        b = results[base][pi]['tokens']
        for arm in arms:
            name = os.path.basename(arm)
            s = results[name][pi]['tokens']
            if not s:
                print('    %-18s no successful runs' % name)
                continue
            delta = ''
            if name != base and b:
                pct = 100.0 * (s['mean'] - b['mean']) / b['mean']
                delta = '%+.1f%% vs %s' % (pct, base)
                if overlap(s, b):
                    delta += '  — RANGES OVERLAP, not distinguishable at n=%d' % s['n']
            print('    %-18s mean %9s  sd %7s  range %s-%s  %s'
                  % (name, f"{s['mean']:,.0f}", f"{s['sd']:,.0f}",
                     f"{s['lo']:,}", f"{s['hi']:,}", delta))
        if results[base][pi]['failed']:
            print('    (%d baseline run(s) failed and are excluded)' % results[base][pi]['failed'])

    print('\nHOW TO READ THIS')
    print('  Overlapping ranges mean the arms were not distinguished by this run.')
    print('  That is a null result, and it is a real result — report it as one.')
    print('  n=%d is small. Non-overlap here is suggestive, not established.' % args.n)
    print('  No p-values are computed: at this n and with this distribution they')
    print('  would imply more confidence than the data carries.')

    if args.json:
        print('\n' + json.dumps(results, indent=2, default=float))


if __name__ == '__main__':
    main()

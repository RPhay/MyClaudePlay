#!/usr/bin/env python3
"""Diagnose a session: what it holds, what filled it, and what it wasted.

Reads a transcript's usage records and its subagent transcripts. Every figure is
a recorded token count; the only estimates are the byte-to-token conversions used
to rank context consumers, and those are labelled.

Usage:
    session.py --root <dir> [--session <id>] [--window <tokens>] [--json]
"""
import argparse, glob, json, os, sys
from collections import Counter, defaultdict
from datetime import datetime

CHARS_PER_TOKEN = 3.6
TTL_MINUTES = 60          # 1-hour cache TTL; a longer gap expires the prefix
BUST_RATIO = 0.6          # cache_read below this fraction of the prior prompt = bust


def slug_for(path):
    return os.path.realpath(path).replace('/', '-')


def project_dir(root):
    return os.path.expanduser('~/.claude/projects/' + slug_for(root))


def pick(root, session):
    d = project_dir(root)
    files = glob.glob(os.path.join(d, '*.jsonl'))
    if not files:
        return None
    if session:
        hit = [f for f in files if session in os.path.basename(f)]
        return hit[0] if hit else None
    return max(files, key=os.path.getmtime)


def ts(rec):
    try:
        return datetime.fromisoformat((rec.get('timestamp') or '').replace('Z', '+00:00'))
    except ValueError:
        return None


# ------------------------------------------------------------------------ scan

def scan(path):
    reqs, adds = [], []
    pending, seen = {}, set()
    for line in open(path, errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        t = rec.get('type')

        if t == 'assistant':
            msg = rec.get('message') or {}
            for b in (msg.get('content') or []) if isinstance(msg.get('content'), list) else []:
                if isinstance(b, dict) and b.get('type') == 'tool_use':
                    pending[b.get('id')] = b.get('name')
            u = msg.get('usage') or {}
            rid = rec.get('requestId')
            if not u or rid in seen:
                continue                       # dedupe: else ~2.2x inflation
            seen.add(rid)
            reqs.append(dict(
                inp=u.get('input_tokens') or 0,
                read=u.get('cache_read_input_tokens') or 0,
                write=u.get('cache_creation_input_tokens') or 0,
                out=u.get('output_tokens') or 0,
                think=(u.get('output_tokens_details') or {}).get('thinking_tokens') or 0,
                model=msg.get('model'), time=ts(rec)))

        elif t == 'user':
            c = (rec.get('message') or {}).get('content')
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get('type') == 'tool_result':
                        body = b.get('content')
                        n = len(body) if isinstance(body, str) else len(json.dumps(body))
                        adds.append((n, pending.get(b.get('tool_use_id'), '?'), 'tool_result'))

        elif t == 'attachment':
            a = rec.get('attachment') or {}
            adds.append((len(json.dumps(a)), str(a.get('type')), 'attachment'))
    return reqs, adds


def busts(reqs):
    """Cache invalidations, with a cause attributed from the record itself."""
    out = []
    for i in range(1, len(reqs)):
        prev, cur = reqs[i - 1], reqs[i]
        prior_total = prev['inp'] + prev['read'] + prev['write']
        if not prior_total or cur['read'] >= prior_total * BUST_RATIO:
            continue
        cause = 'unattributed'
        if cur['model'] != prev['model']:
            cause = 'model switch %s -> %s' % (prev['model'], cur['model'])
        elif cur['time'] and prev['time']:
            gap = (cur['time'] - prev['time']).total_seconds() / 60
            if gap > TTL_MINUTES:
                cause = 'cache TTL expiry after %s' % fmt_gap(gap)
        out.append(dict(index=i, cost=cur['write'], cause=cause))
    return out


def fmt_gap(minutes):
    if minutes < 90:
        return '%d min' % round(minutes)
    return '%.1f h' % (minutes / 60)


def subagents(root, transcript):
    sid = os.path.basename(transcript)[:-6]
    d = os.path.join(project_dir(root), sid, 'subagents')
    rows = []
    for jf in sorted(glob.glob(os.path.join(d, '*.jsonl'))):
        meta = {}
        mf = jf[:-6] + '.meta.json'
        if os.path.isfile(mf):
            try:
                meta = json.load(open(mf))
            except ValueError:
                pass
        seen, tot = set(), Counter()
        for line in open(jf, errors='replace'):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get('type') != 'assistant':
                continue
            u = (rec.get('message') or {}).get('usage') or {}
            rid = rec.get('requestId')
            if not u or rid in seen:
                continue
            seen.add(rid)
            for k, f in (('write', 'cache_creation_input_tokens'),
                         ('read', 'cache_read_input_tokens'),
                         ('out', 'output_tokens')):
                tot[k] += u.get(f) or 0
        rows.append(dict(type=meta.get('agentType', 'agent'),
                         desc=meta.get('description', ''), **tot))
    return rows


# ---------------------------------------------------------------------- report

def tok(chars):
    return round(chars / CHARS_PER_TOKEN)


def report(root, path, reqs, adds, bl, subs, window):
    print('SESSION AUDIT — %s\n' % os.path.basename(path))
    if not reqs:
        print('no usage records in this transcript')
        return
    totals = [r['inp'] + r['read'] + r['write'] for r in reqs]
    cur, peak = totals[-1], max(totals)
    write = sum(r['write'] for r in reqs)
    out = sum(r['out'] for r in reqs)
    think = sum(r['think'] for r in reqs)

    print('OCCUPANCY  (recorded token counts)')
    print('  requests                 %s' % f'{len(reqs):,}')
    print('  current context          %s tokens' % f'{cur:,}')
    print('  peak context             %s tokens' % f'{peak:,}')
    if window:
        print('  of a %s window           %.0f%% now, %.0f%% at peak'
              % (f'{window:,}', 100.0 * cur / window, 100.0 * peak / window))
    print('  output generated         %s tokens (%s thinking)' % (f'{out:,}', f'{think:,}'))
    read = sum(r['read'] for r in reqs)
    denom = read + write + sum(r['inp'] for r in reqs)
    print('  cache read ratio         %.3f' % (read / denom if denom else 0))

    print('\nCACHE INVALIDATION')
    if not bl:
        print('  none — the prefix held for the whole session')
    else:
        lost = sum(b['cost'] for b in bl)
        print('  %d event%s rewrote %s tokens — %.0f%% of all %s written'
              % (len(bl), '' if len(bl) == 1 else 's', f'{lost:,}',
                 100.0 * lost / write if write else 0, f'{write:,}'))
        for b in bl:
            print('    request %-4d %10s tokens   %s' % (b['index'], f"{b['cost']:,}", b['cause']))

    print('\nLARGEST CONTEXT ADDITIONS  (bytes, token figures estimated)')
    agg = defaultdict(int)
    for n, label, kind in adds:
        agg[(kind, label)] += n
    for (kind, label), n in sorted(agg.items(), key=lambda kv: -kv[1])[:8]:
        print('  %-12s %-22s %9s B  ~%s t' % (kind, label[:22], f'{n:,}', f'{tok(n):,}'))

    if subs:
        print('\nSUBAGENTS  (%d)' % len(subs))
        by = defaultdict(lambda: Counter())
        for s in subs:
            by[s['type']]['n'] += 1
            for k in ('write', 'read', 'out'):
                by[s['type']][k] += s[k]
        for t, c in sorted(by.items(), key=lambda kv: -kv[1]['write']):
            print('  %-18s x%-3d cache-write %9s   read %9s   output %7s'
                  % (t, c['n'], f"{c['write']:,}", f"{c['read']:,}", f"{c['out']:,}"))
        ret = sum(n for n, label, kind in adds if kind == 'tool_result' and label in ('Agent', 'Task'))
        tw = sum(c['write'] for c in by.values())
        print('  returned into main context   ~%s tokens' % f'{tok(ret):,}')
        print('  subagent cache writes         %s tokens' % f'{tw:,}')
        print('  These are not comparable as they stand: the subagent cost is a')
        print('  one-time write, while text kept out of context would have been')
        print('  re-read at 0.1x on every remaining turn. Whether delegation paid')
        print('  depends on session length and document size — see the crossover')
        print('  model in CLAUDE-TODO.md. This report does not decide it.')

    print('\nRECOMMENDATION')
    for line in advise(reqs, bl, write, cur, peak, window):
        print('  ' + line)


def advise(reqs, bl, write, cur, peak, window):
    out = []
    lost = sum(b['cost'] for b in bl)
    if write and lost / write > 0.5:
        out.append('%.0f%% of cache writes came from invalidation, not new content.' % (100.0 * lost / write))
        if any('model switch' in b['cause'] for b in bl):
            out.append('Pick a model at session start; switching rewrites the whole prefix.')
        if any('TTL' in b['cause'] for b in bl):
            out.append('Resuming after the 1-hour TTL rebuilds the prefix. Finish or hand off.')
    if window and cur / window > 0.7:
        out.append('Context is over 70%% of the window. Prefer session-handoff then /clear:')
        out.append('compaction re-reads everything to summarise it and drops the reasoning.')
    elif not window:
        out.append('No --window given, so no percentage-of-window claim is made.')
    if not out:
        out.append('Nothing notable. The prefix held and no consumer dominates.')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--session')
    ap.add_argument('--window', type=int)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    root = os.path.realpath(args.root)
    path = pick(root, args.session)
    if not path:
        sys.exit('no transcript found for %s' % root)

    reqs, adds = scan(path)
    bl = busts(reqs)
    subs = subagents(root, path)
    if args.json:
        for r in reqs:
            r['time'] = r['time'].isoformat() if r['time'] else None
        print(json.dumps(dict(transcript=path, requests=reqs, busts=bl,
                              subagents=subs), indent=2))
    else:
        report(root, path, reqs, adds, bl, subs, args.window)


if __name__ == '__main__':
    main()

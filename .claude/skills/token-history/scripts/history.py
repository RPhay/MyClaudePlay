#!/usr/bin/env python3
"""Longitudinal token cost across every recorded session for a project.

The observational counterpart to token-benchmark: a benchmark shows whether a
change helps under controlled conditions, this shows what actually happened over
real work. Its most useful column is the per-session static baseline, which moves
when the repo's fixed overhead changes.

Usage:
    history.py --root <dir> [--all] [--price-in <usd/1M>] [--price-out <usd/1M>] [--json]
"""
import argparse, glob, json, os, sys
from collections import Counter
from datetime import datetime

TTL_MINUTES = 60
BUST_RATIO = 0.6


def slug_for(path):
    return os.path.realpath(path).replace('/', '-')


def ts(rec):
    try:
        return datetime.fromisoformat((rec.get('timestamp') or '').replace('Z', '+00:00'))
    except ValueError:
        return None


def scan_session(path):
    seen, reqs = set(), []
    for line in open(path, errors='replace'):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get('type') != 'assistant':
            continue
        msg = rec.get('message') or {}
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
            model=msg.get('model'), time=ts(rec)))
    if not reqs:
        return None

    totals = [r['inp'] + r['read'] + r['write'] for r in reqs]
    read = sum(r['read'] for r in reqs)
    write = sum(r['write'] for r in reqs)
    inp = sum(r['inp'] for r in reqs)
    out = sum(r['out'] for r in reqs)

    busts = Counter()
    lost = 0
    for i in range(1, len(reqs)):
        prev, cur = reqs[i - 1], reqs[i]
        prior = prev['inp'] + prev['read'] + prev['write']
        if not prior or cur['read'] >= prior * BUST_RATIO:
            continue
        lost += cur['write']
        if cur['model'] != prev['model']:
            busts['model switch'] += 1
        elif cur['time'] and prev['time'] and \
                (cur['time'] - prev['time']).total_seconds() / 60 > TTL_MINUTES:
            busts['TTL expiry'] += 1
        else:
            busts['unattributed'] += 1

    times = [r['time'] for r in reqs if r['time']]
    return dict(
        id=os.path.basename(path)[:8],
        start=min(times) if times else None,
        requests=len(reqs), peak=max(totals),
        baseline=min(r['read'] for r in reqs if r['read']) if any(r['read'] for r in reqs) else 0,
        read=read, write=write, inp=inp, out=out,
        ratio=read / (read + write + inp) if (read + write + inp) else 0.0,
        busts=dict(busts), lost=lost,
        models=sorted({r['model'] for r in reqs if r['model']}))


def sessions_for(root):
    d = os.path.expanduser('~/.claude/projects/' + slug_for(root))
    out = []
    for f in sorted(glob.glob(os.path.join(d, '*.jsonl'))):
        s = scan_session(f)
        if s:
            out.append(s)
    out.sort(key=lambda s: s['start'] or datetime.min.replace(tzinfo=None))
    return out


def money(tokens, rate):
    return tokens * rate / 1_000_000 if rate else None


def report(root, sess, pin, pout):
    print('TOKEN HISTORY — %s\n' % os.path.realpath(root))
    if not sess:
        print('no recorded sessions for this project')
        return

    print('SESSIONS  (%d)' % len(sess))
    hdr = '  %-10s %-8s %5s %10s %9s %10s %10s %6s %s'
    print(hdr % ('date', 'id', 'reqs', 'peak', 'baseline', 'cache-wr', 'output', 'ratio', 'busts'))
    for s in sess:
        d = s['start'].strftime('%Y-%m-%d') if s['start'] else '?'
        b = ','.join('%s x%d' % (k, v) for k, v in s['busts'].items()) or '-'
        print(hdr % (d, s['id'], f"{s['requests']:,}", f"{s['peak']:,}",
                     f"{s['baseline']:,}", f"{s['write']:,}", f"{s['out']:,}",
                     '%.3f' % s['ratio'], b))

    tw = sum(s['write'] for s in sess)
    tr = sum(s['read'] for s in sess)
    to = sum(s['out'] for s in sess)
    tl = sum(s['lost'] for s in sess)
    print('\nTOTALS')
    print('  cache writes         %14s tokens   billed ~2.0x (1-hour TTL)' % f'{tw:,}')
    print('  cache reads          %14s tokens   billed ~0.1x' % f'{tr:,}')
    print('  output               %14s tokens' % f'{to:,}')
    print('  Reads are large because the whole prefix is re-read every turn. At')
    print('  0.1x they are not comparable to writes token-for-token: %s of reads'
          % f'{tr:,}')
    print('  carries roughly the weight of %s of fresh input.' % f'{round(tr * 0.1):,}')
    if tw:
        print('  writes from invalidation %10s tokens  (%.0f%% of all writes)'
              % (f'{tl:,}', 100.0 * tl / tw))
    if pin or pout:
        c = (money(tw + tr, pin) or 0) + (money(to, pout) or 0)
        print('  approx spend         %14s   at %s/%s per 1M in/out'
              % ('$%.2f' % c, pin, pout))
        print('  (input priced flat; cache reads and writes bill at different')
        print('   multipliers, so this is an upper-bound sketch, not a bill)')

    print('\nTREND')
    base = [s['baseline'] for s in sess if s['baseline']]
    if len(base) >= 2:
        first, last = base[0], base[-1]
        delta = last - first
        print('  static baseline      %s -> %s tokens  (%+d)' % (f'{first:,}', f'{last:,}', delta))
        print('  range across sessions %s - %s' % (f'{min(base):,}', f'{max(base):,}'))
        if abs(delta) > 500:
            print('  A moving baseline means the repo\'s fixed overhead changed —')
            print('  a skill, hook, MCP server or CLAUDE.md edit. Run token-overhead-audit.')
        else:
            print('  Baseline is stable; fixed overhead has not materially changed.')
    else:
        print('  too few sessions to show a baseline trend')

    ratios = [s['ratio'] for s in sess]
    if len(ratios) >= 2:
        print('  cache read ratio     %.3f -> %.3f' % (ratios[0], ratios[-1]))
    busty = [s for s in sess if s['busts']]
    print('  sessions with invalidation   %d of %d' % (len(busty), len(sess)))
    causes = Counter()
    for s in sess:
        causes.update(s['busts'])
    if causes:
        print('  causes overall       ' + ', '.join('%s x%d' % (k, v) for k, v in causes.most_common()))

    print('\nThis is observational. Sessions differ in length and task, so a change')
    print('between them is not attributable to any one cause. token-benchmark is')
    print('the controlled test; this only says what actually happened.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--all', action='store_true', help='every project, not just this one')
    ap.add_argument('--price-in', type=float)
    ap.add_argument('--price-out', type=float)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    root = os.path.realpath(args.root)

    if args.all:
        rows = []
        for d in sorted(glob.glob(os.path.expanduser('~/.claude/projects/*'))):
            if not os.path.isdir(d):
                continue
            ss = [scan_session(f) for f in sorted(glob.glob(os.path.join(d, '*.jsonl')))]
            ss = [s for s in ss if s]
            if ss:
                rows.append((os.path.basename(d), len(ss),
                             sum(s['write'] for s in ss), sum(s['out'] for s in ss),
                             max(s['peak'] for s in ss)))
        rows.sort(key=lambda r: -r[2])
        print('ALL PROJECTS  (%d with recorded sessions)\n' % len(rows))
        print('  %-58s %5s %13s %12s %11s' % ('project', 'sess', 'cache-writes', 'output', 'peak'))
        for name, n, w, o, p in rows[:25]:
            print('  %-58s %5d %13s %12s %11s' % (name[-58:], n, f'{w:,}', f'{o:,}', f'{p:,}'))
        return

    sess = sessions_for(root)
    if args.json:
        for s in sess:
            s['start'] = s['start'].isoformat() if s['start'] else None
        print(json.dumps(dict(root=root, sessions=sess), indent=2))
    else:
        report(root, sess, args.price_in, args.price_out)


if __name__ == '__main__':
    main()

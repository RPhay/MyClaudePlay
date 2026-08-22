#!/usr/bin/env python3
"""Emit the mechanically verifiable facts about the current session.

The model supplies what only it knows -- decisions, rejected alternatives, the
next action. This supplies what it should not have to remember: how large the
session got, which files it actually touched, and where git stands.

Usage:
    state.py --root <dir> [--json]
"""
import argparse, glob, json, os, re, shlex, subprocess, sys, time
from collections import Counter, OrderedDict

FRESH_MINUTES = 180        # a transcript older than this is probably not this session
ASSIGN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')


def slug_for(path):
    return os.path.realpath(path).replace('/', '-')


def current_transcript(root):
    d = os.path.expanduser('~/.claude/projects/' + slug_for(root))
    files = glob.glob(os.path.join(d, '*.jsonl'))
    if not files:
        return None
    newest = max(files, key=os.path.getmtime)
    if (time.time() - os.path.getmtime(newest)) / 60 > FRESH_MINUTES:
        return None
    return newest


def scan(path):
    """Occupancy, turns, and the files this session actually wrote."""
    seen = set()
    peak = turns = out_tokens = 0
    edited = OrderedDict()
    bash = Counter()
    agents = Counter()
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
        if u and rid not in seen:
            seen.add(rid)
            turns += 1
            total = ((u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0)
                     + (u.get('cache_creation_input_tokens') or 0))
            peak = max(peak, total)
            out_tokens += u.get('output_tokens') or 0
        for b in (msg.get('content') or []) if isinstance(msg.get('content'), list) else []:
            if not isinstance(b, dict) or b.get('type') != 'tool_use':
                continue
            name, inp = b.get('name'), (b.get('input') or {})
            if name in ('Edit', 'Write', 'NotebookEdit'):
                fp = inp.get('file_path')
                if fp:
                    edited[fp] = edited.get(fp, 0) + 1
            elif name == 'Bash':
                # Quote-aware, so a multi-word VAR='a b c' assignment is skipped
                # whole rather than leaking its contents into the tally.
                try:
                    words = shlex.split(inp.get('command') or '')
                except ValueError:
                    words = []
                for word in words:
                    if ASSIGN.match(word):
                        continue
                    bash[os.path.basename(word)] += 1
                    break
            elif name in ('Agent', 'Task'):
                agents[inp.get('subagent_type') or 'agent'] += 1
    return dict(peak=peak, turns=turns, output=out_tokens,
                edited=edited, bash=bash.most_common(8), agents=dict(agents))


def git(root):
    def run(*a):
        try:
            return subprocess.run(('git', '-C', root) + a, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except Exception:
            return ''
    return dict(branch=run('rev-parse', '--abbrev-ref', 'HEAD'),
                status=run('status', '--porcelain'),
                commits=run('log', '--oneline', '-8'))


def report(root, tr, st, g):
    print('SESSION STATE — %s\n' % os.path.realpath(root))
    if tr:
        print('TRANSCRIPT  %s' % os.path.basename(tr))
        print('  requests            %d' % st['turns'])
        print('  peak context        %s tokens' % f"{st['peak']:,}")
        print('  output generated    %s tokens' % f"{st['output']:,}")
    else:
        print('TRANSCRIPT  none recent — occupancy figures unavailable')

    print('\nGIT')
    print('  branch              %s' % (g['branch'] or 'unknown'))
    dirty = [l for l in g['status'].splitlines() if l.strip()]
    print('  uncommitted         %d path%s' % (len(dirty), '' if len(dirty) == 1 else 's'))
    for l in dirty[:12]:
        print('      %s' % l)
    print('  recent commits')
    for l in g['commits'].splitlines():
        print('      %s' % l)

    if tr:
        print('\nFILES WRITTEN THIS SESSION  (%d)' % len(st['edited']))
        for fp, n in st['edited'].items():
            rel = os.path.relpath(fp, os.path.realpath(root)) if fp.startswith(os.path.realpath(root)) else fp
            print('  %3dx  %s' % (n, rel))
        if st['bash']:
            print('\nCOMMANDS RUN  (top)')
            print('  ' + ', '.join('%s x%d' % (c, n) for c, n in st['bash']))
        if st['agents']:
            print('\nSUBAGENTS  ' + ', '.join('%s x%d' % (k, v) for k, v in st['agents'].items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    root = os.path.realpath(args.root)
    if not os.path.isdir(root):
        sys.exit('not a directory: %s' % root)

    tr = current_transcript(root)
    st = scan(tr) if tr else dict(peak=0, turns=0, output=0, edited={}, bash=[], agents={})
    g = git(root)
    if args.json:
        st['edited'] = list(st['edited'].items())
        print(json.dumps(dict(root=root, transcript=tr, **st, git=g), indent=2))
    else:
        report(root, tr, st, g)


if __name__ == '__main__':
    main()

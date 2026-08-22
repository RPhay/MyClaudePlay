#!/usr/bin/env python3
"""Resolve the CLAUDE.md instruction graph for a working directory and cost it.

Every rule implemented here was measured against Claude Code 2.1.239, not read
from documentation. See ../references/behaviour.md for the evidence behind each.

Usage:
    graph.py --root <dir> [--json] [--all]
"""
import argparse, json, os, re, sys, glob
from collections import defaultdict

MAX_HOP = 4                     # minimum hop distance; hop 5 silently never loads
OVERSIZE_BYTES = 8000           # node size at which detail belongs in a reference
DUP_MIN_CHARS = 30              # ignore short lines when hunting duplicates

FENCE = re.compile(r'^\s*(```|~~~)')
INLINE_CODE = re.compile(r'`[^`]*`')
# '@' must start the line or follow whitespace, so user@example.com is not an import
IMPORT = re.compile(r'(?:^|(?<=\s))@([^\s`"\'<>()\[\],;]+)')
LIST_ITEM = re.compile(r'^\s{0,3}(?:[-*+]|\d+[.)])\s')
BLOCKQUOTE = re.compile(r'^\s*>+\s?')
DUP_JUNK = re.compile(r'[^a-z0-9 ]+')


# --------------------------------------------------------------------------- parse

def extract_imports(path):
    """Yield (raw_path, line_no, alone_on_line) for every live import in a file.

    Suppressed contexts, all verified: fenced blocks (``` and ~~~), inline code
    spans, and 4-space indented blocks.
    """
    out = []
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return out
    fence = None            # the marker that opened the current fence, or None
    in_list = False         # inside a list, indented lines are continuations
    for n, raw in enumerate(lines, 1):
        m = FENCE.match(raw)
        if m:
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:                   # only its own kind closes
                fence = None
            continue
        if fence:
            continue

        stripped = raw.strip()
        indented = raw.startswith('    ') or raw.startswith('\t')
        if LIST_ITEM.match(raw):
            in_list = True
        elif stripped and not indented:
            in_list = False                             # blanks leave it unchanged
        if indented and not in_list:
            continue                                    # true indented code block

        line = INLINE_CODE.sub(' ', raw)                # strip inline code spans
        # For the alone-on-line test, a leading '>' or '- ' is structure, not prose.
        bare = LIST_ITEM.sub('', BLOCKQUOTE.sub('', line)).strip()
        for m in IMPORT.finditer(line):
            target = m.group(1)
            if '/' not in target and '.' not in target:
                continue                                # not path-like
            out.append((target, n, bare == m.group(0).strip()))
    return out


def resolve(target, importer):
    """Resolve an import. Relative paths are relative to the IMPORTING FILE's dir."""
    if target.startswith('~'):
        return None                                     # '~' is never expanded
    if os.path.isabs(target):
        return os.path.realpath(target)
    return os.path.realpath(os.path.join(os.path.dirname(importer), target))


# --------------------------------------------------------------------------- roots

def root_files(root):
    """Root set in load order: user scope, then every ancestor from / down to root.

    The ancestor walk has no boundary -- it does not stop at the git root.
    """
    roots, seen = [], set()
    home = os.path.expanduser('~/.claude')
    for name in ('CLAUDE.md', 'CLAUDE.local.md'):
        p = os.path.realpath(os.path.join(home, name))
        if os.path.isfile(p) and p not in seen:
            seen.add(p)
            roots.append((p, 'user'))

    root = os.path.realpath(root)
    chain, cur = [], root
    while True:
        chain.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    for d in reversed(chain):                           # outermost first
        for name in ('CLAUDE.md', 'CLAUDE.local.md'):
            p = os.path.realpath(os.path.join(d, name))
            if os.path.isfile(p) and p not in seen:
                seen.add(p)
                scope = 'project' if d == root else 'ancestor'
                roots.append((p, scope))
    return roots


# --------------------------------------------------------------------------- walk

def walk(root):
    """Breadth-first over the graph. A node loads if its MINIMUM hop <= MAX_HOP."""
    nodes, findings, maybe_unreachable = {}, [], []
    frontier = []
    for path, scope in root_files(root):
        if path not in nodes:
            nodes[path] = {'path': path, 'hop': 0, 'scope': scope, 'via': None}
            frontier.append(path)

    while frontier:
        nxt = []
        for parent in frontier:
            hop = nodes[parent]['hop']
            for target, line, alone in extract_imports(parent):
                if target.startswith('~'):
                    findings.append(dict(kind='tilde_import', cls=1, file=parent,
                                         line=line, target=target))
                    continue
                dest = resolve(target, parent)
                if not os.path.isfile(dest):
                    findings.append(dict(kind='dead_import', cls=1, file=parent,
                                         line=line, target=target, resolved=dest))
                    continue
                if not alone:
                    findings.append(dict(kind='prose_import', cls=1, file=parent,
                                         line=line, target=target, resolved=dest))
                if hop + 1 > MAX_HOP:
                    # Provisional: a diamond may still reach this node by a
                    # shorter path. Filtered against `nodes` once the walk ends.
                    maybe_unreachable.append(dict(kind='unreachable_import', cls=2,
                                                  file=parent, line=line, target=target,
                                                  resolved=dest, hop=hop + 1))
                    continue
                if dest not in nodes:
                    nodes[dest] = {'path': dest, 'hop': hop + 1, 'scope': 'import',
                                   'via': parent}
                    nxt.append(dest)
        frontier = nxt

    # Minimum hop wins: keep only targets no shorter path reached.
    findings += [f for f in maybe_unreachable if f['resolved'] not in nodes]
    return nodes, findings


# --------------------------------------------------------------------------- cost

def size(path):
    try:
        data = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return 0, 0
    return len(data.encode('utf-8')), len(data.split())


def estimate(nbytes, nwords):
    """Two published methods, reported as a bracket. They differ by ~40%."""
    return sorted((round(nwords * 1.3), nbytes // 4))


def slug_for(path):
    return os.path.realpath(path).replace('/', '-')


def measured_baseline(root):
    """Floor of cache_read_input_tokens across this project's transcripts.

    This is the whole static prefix -- system prompt, tool schemas, skill listing
    AND the instruction graph. It bounds the graph; it does not isolate it.
    """
    d = os.path.expanduser('~/.claude/projects/' + slug_for(root))
    files = glob.glob(os.path.join(d, '*.jsonl'))
    floor, sessions = None, 0
    for f in files:
        seen, local = set(), None
        for line in open(f, errors='replace'):
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
                continue                                # dedupe: ~2.2x inflation
            seen.add(rid)
            cr = u.get('cache_read_input_tokens') or 0
            if cr and (local is None or cr < local):
                local = cr
        if local:
            sessions += 1
            floor = local if floor is None else min(floor, local)
    return floor, sessions


# ----------------------------------------------------------------------- findings

def dup_key(s):
    """Compare duplicates on words alone, so reflow and punctuation do not hide one."""
    return ' '.join(DUP_JUNK.sub(' ', s.lower()).split())


def extra_findings(nodes, root):
    out = []
    root = os.path.realpath(root)
    seen_lines = defaultdict(list)
    for p, meta in nodes.items():
        nbytes, _ = size(p)
        if nbytes > OVERSIZE_BYTES:
            out.append(dict(kind='oversized_node', cls=3, file=p, bytes=nbytes))
        # An import can land outside the repo too, not just an ancestor node.
        if meta['scope'] in ('ancestor', 'import') and not p.startswith(root + os.sep):
            out.append(dict(kind='outside_repo', cls=3, file=p))
        try:
            for raw in open(p, encoding='utf-8', errors='replace'):
                s = raw.strip()
                if len(s) >= DUP_MIN_CHARS and not s.startswith('#'):
                    seen_lines[dup_key(s)].append((p, s))
        except OSError:
            pass
    for _, hits in seen_lines.items():
        uniq = sorted(set(p for p, _ in hits))
        if len(uniq) > 1:
            out.append(dict(kind='duplicate_instruction', cls=2,
                            files=uniq, text=hits[0][1][:110]))
    return out


# -------------------------------------------------------------------------- render

LABEL = {
    'dead_import':        'Dead import (target missing)',
    'tilde_import':       'Tilde import (~ never resolves)',
    'prose_import':       'Accidental import from prose mention',
    'unreachable_import': 'Unreachable import (past hop %d)' % MAX_HOP,
    'duplicate_instruction': 'Instruction duplicated across nodes',
    'oversized_node':     'Oversized node',
    'outside_repo':       'Node outside the repo (global cost)',
}


def report(root, nodes, findings):
    total_b = total_w = 0
    rows = []
    for p, meta in sorted(nodes.items(), key=lambda kv: (kv[1]['hop'], kv[0])):
        b, w = size(p)
        total_b += b
        total_w += w
        lo, hi = estimate(b, w)
        rows.append((p, meta, b, lo, hi))
    lo, hi = estimate(total_b, total_w)

    print('CLAUDE.md INSTRUCTION GRAPH — cwd %s\n' % os.path.realpath(root))
    base, sessions = measured_baseline(root)
    print('MEASURED  (transcripts)')
    if base:
        share_lo, share_hi = 100.0 * lo / base, 100.0 * hi / base
        print('  Fixed prefix baseline        %8s tokens   (%d session%s)'
              % (f'{base:,}', sessions, '' if sessions == 1 else 's'))
        print('  Graph share of baseline      %8s' % ('%.1f%% – %.1f%%' % (share_lo, share_hi)))
        if hi > base:
            print('  !! estimate exceeds baseline — estimator bug, do not trust the bracket')
    else:
        print('  no transcripts for this path — estimate only')

    print('\nESTIMATED (words x1.3 – bytes/4)          [--calibrate for measured]')
    print('  Instruction graph            %8s tokens   %d nodes, %s B'
          % ('%d – %d' % (lo, hi), len(nodes), f'{total_b:,}'))
    print('  First turn   2.0x cache write %7s' % ('%d – %d' % (lo * 2, hi * 2)))
    print('  Each turn after 0.1x read     %7s' % ('%d – %d' % (round(lo * .1), round(hi * .1))))

    print('\nNODES (load order, outermost first)')
    for p, meta, b, l, h in rows:
        print('  %-58s %7s B  %5s t  %s%s'
              % (short(p, 58), f'{b:,}', '%d–%d' % (l, h), meta['scope'],
                 '' if meta['hop'] == 0 else ' hop%d' % meta['hop']))

    print('\nFINDINGS')
    if not findings:
        print('  none')
        return
    by = defaultdict(list)
    for f in findings:
        by[f['kind']].append(f)
    for kind in ('dead_import', 'tilde_import', 'prose_import', 'unreachable_import',
                 'duplicate_instruction', 'outside_repo', 'oversized_node'):
        for f in by.get(kind, []):
            print('  [class %d] %s' % (f['cls'], LABEL[kind]))
            if kind == 'duplicate_instruction':
                print('            "%s"' % f['text'])
                for p in f['files']:
                    print('            in %s' % short(p, 66))
            elif kind == 'outside_repo':
                print('            %s' % f['file'])
            elif kind == 'oversized_node':
                print('            %s (%s B)' % (short(f['file'], 60), f'{f["bytes"]:,}'))
            else:
                print('            %s:%d  ->  @%s' % (short(f['file'], 50), f['line'], f['target']))


def short(p, width):
    home = os.path.expanduser('~')
    if p.startswith(home):
        p = '~' + p[len(home):]
    return p if len(p) <= width else '…' + p[-(width - 1):]


# ---------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, help='working directory to model')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    if not os.path.isdir(args.root):
        sys.exit('not a directory: %s' % args.root)

    nodes, findings = walk(args.root)
    findings += extra_findings(nodes, args.root)

    if args.json:
        base, sessions = measured_baseline(args.root)
        tb = tw = 0
        for p in nodes:
            b, w = size(p)
            tb += b
            tw += w
        lo, hi = estimate(tb, tw)
        print(json.dumps(dict(root=os.path.realpath(args.root),
                              baseline=base, sessions=sessions,
                              bytes=tb, tokens_lo=lo, tokens_hi=hi,
                              nodes=list(nodes.values()),
                              findings=findings), indent=2))
    else:
        report(args.root, nodes, findings)


if __name__ == '__main__':
    main()

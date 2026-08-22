#!/usr/bin/env python3
"""What this codebase's shape costs Claude when it explores.

Two halves, kept apart. The measured half comes from transcripts: files that
actually hit the Read cap, and what reading them actually cost. The inferred half
is filesystem heuristics about files not yet read.

Usage:
    layout.py --root <dir> [--json]
"""
import argparse, glob, json, os, re, sys
from collections import Counter, defaultdict

CHARS_PER_TOKEN = 3.6
DEFAULT_CAP = 25000        # overridden by any cap observed in a truncation notice
FANOUT_WARN = 40           # entries in one directory before it is worth mentioning
HEAVY = ('node_modules', 'dist', 'build', '.next', 'target', 'vendor', '.venv',
         'venv', '__pycache__', 'coverage', '.pytest_cache', '.mypy_cache',
         'out', '.turbo', '.parcel-cache')
SKIP = {'.git'}
# Binary files are never read as text, so a bytes/token estimate is meaningless
# for them. Extension check first, then a NUL sniff for anything unlabelled.
BINARY_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp', '.tiff',
              '.pdf', '.zip', '.gz', '.tar', '.tgz', '.bz2', '.xz', '.7z', '.rar',
              '.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav', '.flac', '.ogg',
              '.woff', '.woff2', '.ttf', '.otf', '.eot', '.so', '.dylib', '.dll',
              '.exe', '.bin', '.class', '.jar', '.pyc', '.wasm', '.db', '.sqlite',
              '.pack', '.idx', '.psd', '.sketch', '.heic'}


def is_text(path):
    if os.path.splitext(path)[1].lower() in BINARY_EXT:
        return False
    try:
        with open(path, 'rb') as fh:
            return b'\0' not in fh.read(8192)
    except OSError:
        return False

TRUNC = re.compile(r'([^\s:]+):\s*showing lines .*?of\s+(\d+)\s+total\s*\((\d+)\s+tokens,\s*cap\s*(\d+)\)')


def slug_for(path):
    return os.path.realpath(path).replace('/', '-')


def transcripts(root):
    return glob.glob(os.path.expanduser('~/.claude/projects/' + slug_for(root)) + '/*.jsonl')


def measured(root):
    """Files that really truncated, and what Read really cost, per transcript."""
    trunc, reads, cap = {}, Counter(), None
    pending = {}
    for f in transcripts(root):
        for line in open(f, errors='replace'):
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
                    if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == 'Read':
                        pending[b.get('id')] = (b.get('input') or {}).get('file_path')
            elif t == 'user':
                c = (rec.get('message') or {}).get('content')
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get('type') == 'tool_result':
                            fp = pending.get(b.get('tool_use_id'))
                            if fp:
                                body = b.get('content')
                                n = len(body) if isinstance(body, str) else len(json.dumps(body))
                                reads[fp] += n
            elif t == 'attachment':
                a = rec.get('attachment') or {}
                if a.get('type') != 'read_truncation_notice':
                    continue
                m = TRUNC.search(str(a.get('banner') or ''))
                if m:
                    path, lines, toks, c = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
                    cap = c
                    prev = trunc.get(path)
                    if prev is None or toks > prev['tokens']:
                        trunc[path] = dict(tokens=toks, lines=lines, cap=c)
    return trunc, reads, cap or DEFAULT_CAP


def walk(root):
    """File sizes and directory fan-out, skipping obviously heavy trees."""
    files, fanout, heavy_present = [], {}, []
    for base, dirs, names in os.walk(root):
        rel = os.path.relpath(base, root)
        parts = set(rel.split(os.sep))
        if parts & SKIP:
            dirs[:] = []
            continue
        for h in list(dirs):
            if h in HEAVY:
                heavy_present.append(os.path.join(rel, h) if rel != '.' else h)
                dirs.remove(h)
        n = len(dirs) + len(names)
        if n >= FANOUT_WARN:
            fanout[rel if rel != '.' else '.'] = n
        for nm in names:
            p = os.path.join(base, nm)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if not is_text(p):
                continue
            files.append((sz, p))
    files.sort(reverse=True)
    return files, fanout, heavy_present


def ignore_state(root):
    ci = os.path.join(root, '.claudeignore')
    if not os.path.isfile(ci):
        return None
    try:
        return set(l.strip().strip('/') for l in open(ci, errors='replace')
                   if l.strip() and not l.startswith('#'))
    except OSError:
        return set()


def tok(nbytes):
    return round(nbytes / CHARS_PER_TOKEN)


def rel(p, root):
    return os.path.relpath(p, root) if p.startswith(root) else p


def report(root, trunc, reads, cap, files, fanout, heavy, ignored):
    print('LAYOUT COST — %s\n' % root)

    print('MEASURED  (from this project\'s transcripts)')
    if trunc:
        print('  files that actually hit the %s-token Read cap:' % f'{cap:,}')
        for p, d in sorted(trunc.items(), key=lambda kv: -kv[1]['tokens']):
            print('    %-52s %8s tokens, %s lines' % (rel(p, root)[:52], f"{d['tokens']:,}", f"{d['lines']:,}"))
    else:
        print('  no Read hit the cap in any recorded session')
    if reads:
        print('  most-read files, by bytes actually returned:')
        for p, n in reads.most_common(5):
            print('    %-52s %8s B  ~%s t' % (rel(p, root)[:52], f'{n:,}', f'{tok(n):,}'))
    else:
        print('  no Read calls recorded')

    print('\nINFERRED  (filesystem; these files may never be read at all)')
    big = [(s, p) for s, p in files if tok(s) > cap]
    if big:
        print('  files large enough to truncate if read whole:')
        for s, p in big[:8]:
            print('    %-52s %8s B  ~%s t' % (rel(p, root)[:52], f'{s:,}', f'{tok(s):,}'))
    else:
        print('  no file is large enough to truncate a Read')
    if fanout:
        print('  wide directories:')
        for d, n in sorted(fanout.items(), key=lambda kv: -kv[1])[:5]:
            print('    %-52s %d entries' % (d[:52], n))

    print('\nFINDINGS')
    out = []
    for p, d in sorted(trunc.items(), key=lambda kv: -kv[1]['tokens']):
        out.append('  [class 3] %s truncated at %s of %s tokens — split it, or read it by section'
                   % (rel(p, root), f"{d['cap']:,}", f"{d['tokens']:,}"))
    if ignored is None and heavy:
        out.append('  [class 1] no .claudeignore, and these heavy trees exist: %s'
                   % ', '.join(sorted(set(heavy))[:6]))
    elif heavy:
        missing = sorted(set(h for h in heavy if os.path.basename(h) not in ignored
                             and h not in ignored))
        if missing:
            out.append('  [class 1] .claudeignore does not cover: %s' % ', '.join(missing[:6]))
    for s, p in big[:3]:
        if p not in trunc:
            out.append('  [class 3] %s is ~%s tokens — a whole-file Read would truncate'
                       % (rel(p, root), f'{tok(s):,}'))
    print('\n'.join(out) if out else '  none')

    print('\nThe MEASURED block is what happened. The INFERRED block is a guess about')
    print('files that may never be read; treat it as a prompt to look, not a defect.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    root = os.path.realpath(args.root)
    if not os.path.isdir(root):
        sys.exit('not a directory: %s' % root)

    trunc, reads, cap = measured(root)
    files, fanout, heavy = walk(root)
    ignored = ignore_state(root)
    if args.json:
        print(json.dumps(dict(root=root, cap=cap, truncated=trunc,
                              reads=reads.most_common(20),
                              largest=[(s, p) for s, p in files[:20]],
                              fanout=fanout, heavy=heavy,
                              claudeignore=sorted(ignored) if ignored else None), indent=2))
    else:
        report(root, trunc, reads, cap, files, fanout, heavy, ignored)


if __name__ == '__main__':
    main()

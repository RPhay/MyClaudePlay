#!/usr/bin/env python3
"""Account for the fixed context cost a repo imposes before any work happens.

Reads this project's transcripts and sizes each component that lands in the
cached prefix, then sets the total against the one measured figure available --
the floor of cache_read_input_tokens -- and states plainly how much is
unaccounted for.

Usage:
    overhead.py --root <dir> [--json]
"""
import argparse, glob, json, os, sys
from collections import defaultdict

CHARS_PER_TOKEN = 3.6      # measured: a 120-char skill description cost 33 tokens
HOOK_WARN = 4000           # chars of SessionStart output worth questioning
LISTED_SKILLS_WARN = 8     # skills in the listing before it is worth pruning

# attachment type -> (label, how to size it)
COMPONENTS = {
    'hook_success':          'SessionStart hook output',
    'skill_listing':         'Skill listing',
    'deferred_tools_delta':  'Deferred tool block',
    'agent_listing_delta':   'Agent listing',
    'mcp_instructions_delta': 'MCP server instructions',
}
PER_TURN = {'total_tokens_reminder': 'Token-budget reminder'}


def slug_for(path):
    return os.path.realpath(path).replace('/', '-')


def transcripts(root):
    d = os.path.expanduser('~/.claude/projects/' + slug_for(root))
    return sorted(glob.glob(os.path.join(d, '*.jsonl')), key=os.path.getmtime)


def scan(files):
    """MOST RECENT size per component, plus the measured baseline.

    Components are taken from the newest transcript that recorded them, not the
    largest ever seen: the report answers what this repo costs now. The baseline
    stays a floor across all sessions, because that is what a floor means.
    """
    comp = {}
    per_turn = {}
    hooks = []
    floor, sessions, turns = None, 0, 0
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
            t = rec.get('type')

            if t == 'assistant':
                u = (rec.get('message') or {}).get('usage') or {}
                rid = rec.get('requestId')
                if not u or rid in seen:
                    continue            # dedupe by requestId: else ~2.2x inflation
                seen.add(rid)
                turns += 1
                cr = u.get('cache_read_input_tokens') or 0
                if cr and (local is None or cr < local):
                    local = cr

            elif t == 'attachment':
                a = rec.get('attachment') or {}
                kind = a.get('type')
                size = len(json.dumps(a))
                if kind == 'hook_success':
                    size = len(str(a.get('stdout') or a.get('content') or ''))
                    # One entry per distinct hook, holding its MOST RECENT output.
                    # Transcripts are iterated oldest-first, so later writes win:
                    # the question is what this repo costs now, not at its worst.
                    key = (a.get('hookName'), a.get('hookEvent'))
                    prior = next((h for h in hooks if (h['name'], h['event']) == key), None)
                    if prior is None:
                        hooks.append(dict(name=key[0], event=key[1],
                                          ms=a.get('durationMs'), chars=size))
                    else:
                        prior['chars'], prior['ms'] = size, a.get('durationMs')
                if kind in COMPONENTS:
                    detail = a.get('skillCount') if kind == 'skill_listing' else None
                    names = a.get('names') if kind == 'skill_listing' else None
                    comp[kind] = dict(chars=size, detail=detail, names=names or [])
                elif kind in PER_TURN:
                    size = len(str(a.get('text') or ''))
                    e = per_turn.setdefault(kind, dict(chars=size, count=0))
                    e['count'] += 1
                    e['chars'] = max(e['chars'], size)
        if local:
            sessions += 1
            floor = local if floor is None else min(floor, local)
    return comp, per_turn, hooks, floor, sessions, turns


def claude_md_bytes(root):
    """Sized here only as a line item; claude-md-audit resolves the real graph."""
    total = 0
    for p in (os.path.expanduser('~/.claude/CLAUDE.md'),
              os.path.expanduser('~/.claude/CLAUDE.local.md'),
              os.path.join(root, 'CLAUDE.md'),
              os.path.join(root, 'CLAUDE.local.md')):
        if os.path.isfile(p):
            total += os.path.getsize(p)
    return total


def tok(chars):
    return round(chars / CHARS_PER_TOKEN)


def report(root, comp, per_turn, hooks, floor, sessions, turns, md_bytes):  # noqa: C901
    print('FIXED PER-TURN OVERHEAD — %s\n' % os.path.realpath(root))

    print('MEASURED')
    if floor:
        print('  Static prefix baseline    %9s tokens   (%d session%s, %d requests)'
              % (f'{floor:,}', sessions, '' if sessions == 1 else 's', turns))
    else:
        print('  no transcripts for this path — components only, no baseline')

    print('\nCOMPONENTS IN THE CACHED PREFIX   (most recent observation)')
    rows, accounted = [], 0
    for kind, label in COMPONENTS.items():
        if kind not in comp:
            continue
        c = comp[kind]['chars']
        if kind == 'hook_success':
            c = sum(h['chars'] for h in hooks)
        extra = ''
        if kind == 'skill_listing' and comp[kind]['detail']:
            extra = '%d skills' % comp[kind]['detail']
        if kind == 'hook_success':
            extra = '%d hook%s' % (len(hooks), '' if len(hooks) == 1 else 's')
        rows.append((label, c, tok(c), extra))
        accounted += tok(c)
    if md_bytes:
        rows.append(('CLAUDE.md graph (roots only)', md_bytes, tok(md_bytes),
                     'run claude-md-audit'))
        accounted += tok(md_bytes)
    if not rows:
        print('  none observed')
    for label, c, t, extra in rows:
        print('  %-30s %8s ch %8s t   %s' % (label, f'{c:,}', f'~{t:,}', extra))

    if floor:
        print('  %-30s %8s    %8s t   %.0f%% of baseline'
              % ('accounted', '', f'~{accounted:,}', 100.0 * accounted / floor))
        rest = floor - accounted
        print('  %-30s %8s    %8s t   %.0f%%   system prompt + tool schemas'
              % ('unaccounted', '', f'~{rest:,}', 100.0 * rest / floor))
        if rest < 0:
            print('  !! accounted exceeds the measured baseline — the estimate is wrong')

    if per_turn:
        print('\nPER TURN, NOT CACHED')
        for kind, e in per_turn.items():
            print('  %-30s %8s ch %8s t   x%d turns'
                  % (PER_TURN[kind], f"{e['chars']:,}", f"~{tok(e['chars']):,}", e['count']))

    print('\nFINDINGS')
    found = []
    for h in hooks:
        if h['chars'] > HOOK_WARN:
            found.append('  [class 3] %s emits %s chars (~%s t) every session start, %s ms'
                         % (h['name'], f"{h['chars']:,}", f"{tok(h['chars']):,}", h['ms']))
    sl = comp.get('skill_listing')
    if sl and (sl['detail'] or 0) > LISTED_SKILLS_WARN:
        # Say where they come from: skill-lint --scope project can only act on
        # this repo's own, and pruning someone else's plugin is a different job.
        proj = os.path.join(os.path.realpath(root), '.claude', 'skills')
        mine = [n for n in sl.get('names') or []
                if os.path.isdir(os.path.join(proj, n))]
        other = (sl['detail'] or 0) - len(mine)
        found.append('  [class 2] %d skills listed, ~%s t every turn — %d from this '
                     'project, %d from user or plugin scope'
                     % (sl['detail'], f"{tok(sl['chars']):,}", len(mine), other))
        if mine:
            found.append('            skill-lint --scope project covers: %s'
                         % ', '.join(sorted(mine)))
        if other:
            found.append('            the rest are installed elsewhere; pruning them '
                         'means uninstalling a plugin, not editing this repo')
    if md_bytes > 4000:
        found.append('  [class 2] CLAUDE.md roots total %s B — run claude-md-audit'
                     % f'{md_bytes:,}')
    print('\n'.join(found) if found else '  none')

    print('\nThis skill only reports. Fixes live in skill-lint (listing) and')
    print('claude-md-audit (instruction graph); hooks and MCP servers are yours.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    if not os.path.isdir(args.root):
        sys.exit('not a directory: %s' % args.root)

    files = transcripts(args.root)
    comp, per_turn, hooks, floor, sessions, turns = scan(files)
    md = claude_md_bytes(os.path.realpath(args.root))
    if args.json:
        print(json.dumps(dict(root=os.path.realpath(args.root), baseline=floor,
                              sessions=sessions, requests=turns, components=comp,
                              per_turn=per_turn, hooks=hooks,
                              claude_md_bytes=md), indent=2))
    else:
        report(args.root, comp, per_turn, hooks, floor, sessions, turns, md)


if __name__ == '__main__':
    main()

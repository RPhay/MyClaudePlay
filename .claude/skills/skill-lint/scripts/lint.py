#!/usr/bin/env python3
"""Check SKILL.md files for conformance defects, and cost their listing overhead.

Every defect checked here was found in real community skill collections; see
../references/defects.md for which, and for the measurement behind the cost
figures.

Usage:
    lint.py [--scope project|user|all] [--root <dir>] [--json]
"""
import argparse, json, os, re, sys, glob
from collections import defaultdict

DESC_LIMIT = 1024          # hard limit on the description field
BODY_WARN = 8000           # bytes above which detail belongs in references/
OVERLAP_MIN = 0.55         # Jaccard on description words; inferred, not measured
CHARS_PER_TOKEN = 3.6      # measured: 120-char description cost 33 listing tokens

FM = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n', re.S)
KEY = re.compile(r'^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$')
WORD = re.compile(r'[a-z0-9]+')


# --------------------------------------------------------------------- discovery

def skill_dirs(scope, root, path=None):
    """Every directory holding a SKILL.md, per scope.

    --path overrides the scopes entirely and scans one directory, which is how
    an unfamiliar collection gets vetted before it is installed anywhere.
    """
    if path:
        return sorted(set(os.path.realpath(p) for p in
                          glob.glob(os.path.join(path, '**', 'SKILL.md'), recursive=True)))
    roots = []
    if scope in ('project', 'all'):
        roots.append(os.path.join(root, '.claude', 'skills'))
    if scope in ('user', 'all'):
        roots.append(os.path.expanduser('~/.claude/skills'))
        roots.append(os.path.expanduser('~/.claude/plugins'))
    out = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        for p in glob.glob(os.path.join(r, '**', 'SKILL.md'), recursive=True):
            out.append(os.path.realpath(p))
    return sorted(set(out))


def empty_skill_dirs(scope, root, path=None):
    """Immediate subdirectories of a skills root holding no SKILL.md at all.

    They occupy a skill slot and can never load. Found in the wild.
    """
    if path:
        roots = [path]
    else:
        roots = []
        if scope in ('project', 'all'):
            roots.append(os.path.join(root, '.claude', 'skills'))
        if scope in ('user', 'all'):
            roots.append(os.path.expanduser('~/.claude/skills'))
    out = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        for d in sorted(os.listdir(r)):
            full = os.path.join(r, d)
            if not os.path.isdir(full) or d.startswith('.'):
                continue
            if not glob.glob(os.path.join(full, '**', 'SKILL.md'), recursive=True):
                out.append(dict(kind='no_skill_file', cls=3, dir=full))
    return out


def scope_of(path):
    if path.startswith(os.path.expanduser('~/.claude/plugins')):
        return 'plugin'
    if path.startswith(os.path.expanduser('~/.claude/skills')):
        return 'user'
    return 'project'


# ------------------------------------------------------------------------ parse

def parse(path):
    """Return (frontmatter dict, body, raw). Keys absent rather than guessed."""
    try:
        raw = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return None, '', ''
    m = FM.match(raw)
    if not m:
        return None, raw, raw                     # no frontmatter at all
    fm, body = {}, raw[m.end():]
    key = None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        km = KEY.match(line)
        if km and not line.startswith((' ', '\t')):
            key = km.group(1)
            fm[key] = km.group(2).strip()
        elif key and line.startswith((' ', '\t')):
            fm[key] = (fm[key] + ' ' + line.strip()).strip()   # folded value
    return fm, body, raw


def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
        return v[1:-1]
    return v


# ---------------------------------------------------------------------- checks

def check(path, fm, body, raw):
    out = []
    d = os.path.basename(os.path.dirname(path))

    if fm is None:
        out.append(dict(kind='no_frontmatter', cls=2, file=path, dir=d))
        return out                                 # everything else is moot

    name = unquote(fm.get('name', ''))
    desc = unquote(fm.get('description', ''))

    if not name:
        out.append(dict(kind='missing_name', cls=1, file=path, dir=d))
    elif name != d:
        out.append(dict(kind='name_dir_mismatch', cls=1, file=path,
                        dir=d, name=name))
    if not desc:
        out.append(dict(kind='missing_description', cls=1, file=path))
    elif len(desc) > DESC_LIMIT:
        out.append(dict(kind='description_too_long', cls=1, file=path,
                        chars=len(desc)))

    nbytes = len(body.encode('utf-8'))
    if nbytes > BODY_WARN:
        siblings = supporting_files(path)
        out.append(dict(kind='oversized_body', cls=2, file=path,
                        bytes=nbytes, supporting=siblings))

    if 'disable-model-invocation' not in fm and desc:
        out.append(dict(kind='always_listed', cls=3, file=path,
                        tokens=round(len(name + desc) / CHARS_PER_TOKEN)))
    return out


def supporting_files(path):
    d = os.path.dirname(path)
    n = 0
    for base, _, files in os.walk(d):
        for f in files:
            if os.path.join(base, f) != path:
                n += 1
    return n


def cross_checks(skills):
    """Defects only visible across the whole set."""
    out = []
    by_name = defaultdict(list)
    for s in skills:
        if s['name']:
            by_name[s['name']].append(s)
    for name, group in sorted(by_name.items()):
        if len(group) > 1:
            out.append(dict(kind='duplicate_name', cls=3, name=name,
                            files=[g['file'] for g in group]))

    # Overlap is INFERRED -- word-set similarity, not meaning.
    for i, a in enumerate(skills):
        for b in skills[i + 1:]:
            if not a['desc'] or not b['desc']:
                continue
            wa, wb = set(WORD.findall(a['desc'].lower())), set(WORD.findall(b['desc'].lower()))
            if len(wa) < 5 or len(wb) < 5:
                continue
            j = len(wa & wb) / len(wa | wb)
            if j >= OVERLAP_MIN:
                out.append(dict(kind='overlapping_description', cls=3,
                                files=[a['file'], b['file']], jaccard=round(j, 2)))
    return out


# ---------------------------------------------------------------------- render

LABEL = {
    'no_frontmatter':         'No frontmatter — invocable by directory, but can never auto-trigger',
    'missing_name':           'Frontmatter has no name',
    'name_dir_mismatch':      'name field disagrees with its directory (the directory is what counts)',
    'missing_description':    'Frontmatter has no description',
    'description_too_long':   'description exceeds %d chars' % DESC_LIMIT,
    'oversized_body':         'Oversized body — detail belongs in references/',
    'duplicate_name':         'Two skills declare the same name field (not a functional collision)',
    'always_listed':          'Listed to the model on every turn',
    'overlapping_description': 'Descriptions overlap — may compete for triggers',
    'no_skill_file':          'Directory in a skills root with no SKILL.md — can never load',
}


def short(p, width=64):
    home = os.path.expanduser('~')
    if p.startswith(home):
        p = '~' + p[len(home):]
    return p if len(p) <= width else '…' + p[-(width - 1):]


def report(skills, findings):
    print('SKILL.md CONFORMANCE — %d skill%s\n'
          % (len(skills), '' if len(skills) == 1 else 's'))

    listed = [s for s in skills if s['always_listed']]
    cost = sum(round(len(s['name'] + s['desc']) / CHARS_PER_TOKEN) for s in listed)
    print('LISTING COST (estimated, %s chars/token)' % CHARS_PER_TOKEN)
    print('  %d of %d skills listed to the model every turn' % (len(listed), len(skills)))
    print('  approx %d tokens in the cached prefix, always' % cost)
    print('  skills with disable-model-invocation cost exactly zero\n')

    print('SKILLS')
    for s in sorted(skills, key=lambda x: (x['scope'], x['dir'])):
        flag = '' if not s['defects'] else '  <- %d defect%s' % (
            s['defects'], '' if s['defects'] == 1 else 's')
        print('  %-8s %-28s %5s B body  %4s desc%s'
              % (s['scope'], s['dir'][:28], f"{s['bytes']:,}", len(s['desc']), flag))

    print('\nFINDINGS')
    if not findings:
        print('  none')
        return
    order = ('no_skill_file', 'no_frontmatter', 'missing_name', 'missing_description',
             'name_dir_mismatch', 'description_too_long', 'duplicate_name',
             'oversized_body', 'overlapping_description', 'always_listed')
    by = defaultdict(list)
    for f in findings:
        by[f['kind']].append(f)
    for kind in order:
        for f in by.get(kind, []):
            print('  [class %d] %s' % (f['cls'], LABEL[kind]))
            if kind == 'duplicate_name':
                print('            name: %s' % f['name'])
                for p in f['files']:
                    print('            %s' % short(p))
            elif kind == 'overlapping_description':
                print('            jaccard %.2f' % f['jaccard'])
                for p in f['files']:
                    print('            %s' % short(p))
            elif kind == 'name_dir_mismatch':
                print('            %s' % short(f['file']))
                print('            declares "%s" in directory "%s"' % (f['name'], f['dir']))
            elif kind == 'oversized_body':
                print('            %s (%s B, %d supporting file%s)'
                      % (short(f['file']), f'{f["bytes"]:,}', f['supporting'],
                         '' if f['supporting'] == 1 else 's'))
            elif kind == 'always_listed':
                print('            %s (~%d tokens/turn)' % (short(f['file']), f['tokens']))
            elif kind == 'description_too_long':
                print('            %s (%d chars)' % (short(f['file']), f['chars']))
            elif kind == 'no_skill_file':
                print('            %s' % short(f['dir']))
            else:
                print('            %s' % short(f['file']))


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', default='all', choices=('project', 'user', 'all'))
    ap.add_argument('--root', default='.')
    ap.add_argument('--path', help='scan an arbitrary directory instead of the scopes')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    skills, findings = [], []
    for path in skill_dirs(args.scope, os.path.realpath(args.root), args.path):
        fm, body, raw = parse(path)
        fs = check(path, fm, body, raw)
        findings += fs
        skills.append(dict(
            file=path, dir=os.path.basename(os.path.dirname(path)),
            scope=scope_of(path),
            name=unquote((fm or {}).get('name', '')),
            desc=unquote((fm or {}).get('description', '')),
            bytes=len(body.encode('utf-8')),
            always_listed=bool(fm) and 'disable-model-invocation' not in fm,
            defects=len(fs)))
    findings += cross_checks(skills)
    findings += empty_skill_dirs(args.scope, os.path.realpath(args.root), args.path)

    if args.json:
        print(json.dumps(dict(skills=skills, findings=findings), indent=2))
    else:
        report(skills, findings)


if __name__ == '__main__':
    main()

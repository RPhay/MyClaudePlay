#!/usr/bin/env python3
"""Unit tests for the token-optimization skill scripts. No model calls, no cost.

    ./tests/unit/skills.test.py            # all
    ./tests/unit/skills.test.py graph      # filter by name

Every case builds throwaway files under $TMPDIR and imports the real script by
path, so nothing touches the working repository.

Each assertion here corresponds to a behaviour measured against Claude Code
2.1.239 and recorded in CLAUDE-TODO.md. When a test fails, check whether the
product changed before changing the test.
"""
import importlib.util, json, os, re, shutil, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(ROOT, '.claude', 'skills')

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def load(skill, script):
    path = os.path.join(SKILLS, skill, 'scripts', script)
    spec = importlib.util.spec_from_file_location('m_' + skill.replace('-', '_'), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tmpdir():
    d = tempfile.mkdtemp(prefix='skilltest-')
    TMPS.append(d)
    return d


TMPS = []


def write(base, rel, text):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return p


def eq(got, want, what):
    assert got == want, '%s: got %r, want %r' % (what, got, want)


# ------------------------------------------------------------------ graph.py

G = load('claude-md-audit', 'graph.py')


def imports_of(text):
    d = tmpdir()
    p = write(d, 'CLAUDE.md', text)
    return G.extract_imports(p)


@case
def graph_fenced_backtick_suppresses():
    eq(imports_of('a\n\n```\n@x.md\n```\n'), [], 'backtick fence')


@case
def graph_fenced_tilde_suppresses():
    eq(imports_of('a\n\n~~~\n@x.md\n~~~\n'), [], 'tilde fence')


@case
def graph_inline_code_suppresses():
    eq(imports_of('see `@x.md` here\n'), [], 'inline code span')


@case
def graph_indented_code_block_suppresses():
    # A paragraph, blank line, then 4-space indent: a real code block.
    eq(imports_of('Example below:\n\n    @x.md\n'), [], 'indented code block')


@case
def graph_list_continuation_imports():
    # Same indent under a list item is a continuation, NOT a code block.
    got = imports_of('- item one:\n\n    @x.md\n')
    eq([t for t, _l, _a in got], ['x.md'], 'list continuation imports')


@case
def graph_two_space_indent_imports():
    got = imports_of('- item:\n  @x.md\n')
    eq([t for t, _l, _a in got], ['x.md'], 'two-space indent imports')


@case
def graph_blockquote_imports_and_is_not_prose():
    got = imports_of('> @x.md\n')
    eq([(t, a) for t, _l, a in got], [('x.md', True)], 'blockquote is a bare import')


@case
def graph_list_marker_import_is_not_prose():
    got = imports_of('- @x.md\n')
    eq([(t, a) for t, _l, a in got], [('x.md', True)], 'list marker stripped for alone test')


@case
def graph_midsentence_is_flagged_prose():
    got = imports_of('See @x.md for details.\n')
    eq([(t, a) for t, _l, a in got], [('x.md', False)], 'prose mention flagged')


@case
def graph_mismatched_fence_does_not_close():
    # ``` opened, ~~~ must not close it, so the import stays suppressed.
    eq(imports_of('```\n~~~\n@x.md\n'), [], 'mismatched fence')


@case
def graph_email_is_not_an_import():
    eq(imports_of('mail me at user@example.com\n'), [], 'email is not an import')


@case
def graph_resolves_against_importing_file():
    d = tmpdir()
    write(d, 'sub/g.md', '')
    write(d, 'i.md', '')
    write(d, 'sub/i.md', '')
    got = G.resolve('i.md', os.path.join(d, 'sub', 'g.md'))
    eq(os.path.realpath(got), os.path.realpath(os.path.join(d, 'sub', 'i.md')),
       'relative resolves against importing file, not project root')


@case
def graph_tilde_never_resolves():
    eq(G.resolve('~/anything.md', '/tmp/CLAUDE.md'), None, 'tilde import')


def walk_isolated(d):
    """walk() with only the fixture as root -- no ancestors, no user scope."""
    real = G.root_files
    G.root_files = lambda root: [(os.path.realpath(os.path.join(d, 'CLAUDE.md')), 'project')]
    try:
        return G.walk(d)
    finally:
        G.root_files = real


@case
def graph_depth_limit_is_four_hops():
    d = tmpdir()
    write(d, 'CLAUDE.md', '@a.md\n')
    for a, b in (('a', 'b'), ('b', 'c'), ('c', 'd'), ('d', 'e')):
        write(d, a + '.md', '@%s.md\n' % b)
    write(d, 'e.md', 'end\n')
    nodes, findings = walk_isolated(d)
    names = sorted(os.path.basename(p) for p in nodes)
    eq(names, ['CLAUDE.md', 'a.md', 'b.md', 'c.md', 'd.md'], 'hops 1-4 load')
    eq([f['target'] for f in findings if f['kind'] == 'unreachable_import'], ['e.md'],
       'hop 5 reported unreachable')


@case
def graph_diamond_minimum_hop_wins():
    d = tmpdir()
    write(d, 'CLAUDE.md', '@p1.md\n\n@q1.md\n')
    for a, b in (('p1', 'p2'), ('p2', 'p3'), ('p3', 'p4')):
        write(d, a + '.md', '@%s.md\n' % b)
    write(d, 'p4.md', '@target.md\n')      # target at hop 5 this way
    write(d, 'q1.md', '@target.md\n')      # and hop 2 that way
    write(d, 'target.md', 'x\n')
    nodes, findings = walk_isolated(d)
    assert any(os.path.basename(p) == 'target.md' for p in nodes), 'target loads by short path'
    eq([f for f in findings if f['kind'] == 'unreachable_import'], [],
       'no false unreachable when a shorter path exists')


@case
def graph_cycle_terminates():
    d = tmpdir()
    write(d, 'CLAUDE.md', '@a.md\n')
    write(d, 'a.md', '@b.md\n')
    write(d, 'b.md', '@a.md\n')
    nodes, _ = walk_isolated(d)
    eq(sorted(os.path.basename(p) for p in nodes), ['CLAUDE.md', 'a.md', 'b.md'], 'cycle loads once')


@case
def graph_dead_import_reported():
    d = tmpdir()
    write(d, 'CLAUDE.md', '@missing.md\n')
    _, findings = walk_isolated(d)
    eq([f['target'] for f in findings if f['kind'] == 'dead_import'], ['missing.md'], 'dead import')


@case
def graph_tilde_import_reported():
    d = tmpdir()
    write(d, 'CLAUDE.md', '@~/nowhere.md\n')
    _, findings = walk_isolated(d)
    eq([f['kind'] for f in findings if f['kind'] == 'tilde_import'], ['tilde_import'], 'tilde import')


# ------------------------------------------------------------------- lint.py

L = load('skill-lint', 'lint.py')


def skillset(**skills):
    d = tmpdir()
    for name, body in skills.items():
        write(d, os.path.join(name.replace('_', '-'), 'SKILL.md'), body)
    return d


def lint(d):
    findings = []
    rows = []
    for p in L.skill_dirs('all', d, d):
        fm, body, raw = L.parse(p)
        findings += L.check(p, fm, body, raw)
        rows.append(dict(file=p, dir=os.path.basename(os.path.dirname(p)),
                         scope='scanned',
                         name=L.unquote((fm or {}).get('name', '')),
                         desc=L.unquote((fm or {}).get('description', '')),
                         bytes=len(body.encode()), always_listed=bool(fm), defects=0))
    findings += L.cross_checks(rows)
    findings += L.empty_skill_dirs('all', d, d)
    return [f['kind'] for f in findings]


@case
def lint_detects_missing_frontmatter():
    d = skillset(alpha='# Alpha\n\nno frontmatter here\n')
    assert 'no_frontmatter' in lint(d), 'no_frontmatter'


@case
def lint_detects_missing_name():
    d = skillset(alpha='---\ndescription: Does a thing when asked to.\n---\n\nbody\n')
    assert 'missing_name' in lint(d), 'missing_name'


@case
def lint_detects_name_dir_mismatch():
    d = skillset(alpha='---\nname: not-alpha\ndescription: Does a thing.\n---\n\nbody\n')
    assert 'name_dir_mismatch' in lint(d), 'name_dir_mismatch'


@case
def lint_accepts_matching_name():
    d = skillset(alpha='---\nname: alpha\ndescription: Does a thing when asked.\n---\n\nbody\n')
    kinds = lint(d)
    assert 'name_dir_mismatch' not in kinds and 'missing_name' not in kinds, kinds


@case
def lint_detects_duplicate_name():
    d = skillset(alpha='---\nname: same\ndescription: One thing.\n---\n\nb\n',
                 beta='---\nname: same\ndescription: Another thing.\n---\n\nb\n')
    assert 'duplicate_name' in lint(d), 'duplicate_name'


@case
def lint_detects_empty_skill_directory():
    d = tmpdir()
    os.makedirs(os.path.join(d, 'hollow'))
    write(d, 'real/SKILL.md', '---\nname: real\ndescription: x y z.\n---\n\nb\n')
    assert 'no_skill_file' in lint(d), 'no_skill_file'


@case
def lint_parses_folded_description():
    d = skillset(alpha='---\nname: alpha\ndescription: first part\n  and second part\n---\n\nb\n')
    p = L.skill_dirs('all', d, d)[0]
    fm, _b, _r = L.parse(p)
    eq(fm['description'], 'first part and second part', 'folded value joined')


@case
def lint_flags_overlong_description():
    d = skillset(alpha='---\nname: alpha\ndescription: %s\n---\n\nb\n' % ('x' * 1100))
    assert 'description_too_long' in lint(d), 'description_too_long'


@case
def lint_disable_model_invocation_is_not_always_listed():
    d = skillset(alpha='---\nname: alpha\ndescription: Does a thing.\n'
                       'disable-model-invocation: true\n---\n\nb\n')
    assert 'always_listed' not in lint(d), 'flagged despite the flag'


# --------------------------------------------------------- transcript fixtures

def usage(read=0, write_=0, inp=0, out=0, think=0):
    return dict(input_tokens=inp, cache_read_input_tokens=read,
                cache_creation_input_tokens=write_, output_tokens=out,
                output_tokens_details=dict(thinking_tokens=think))


def assistant(rid, u, model='claude-opus-5', when=None, content=None):
    r = dict(type='assistant', requestId=rid,
             message=dict(model=model, usage=u, content=content or []))
    if when:
        r['timestamp'] = when.isoformat().replace('+00:00', 'Z')
    return r


def transcript(records):
    d = tmpdir()
    p = os.path.join(d, 'sess.jsonl')
    with open(p, 'w', encoding='utf-8') as fh:
        for r in records:
            fh.write(json.dumps(r) + '\n')
    return p


# ---------------------------------------------------------------- session.py

S = load('token-session-audit', 'session.py')


@case
def session_dedupes_by_request_id():
    p = transcript([assistant('r1', usage(read=100, write_=10)),
                    assistant('r1', usage(read=100, write_=10)),
                    assistant('r2', usage(read=110, write_=5))])
    reqs, _adds = S.scan(p)
    eq(len(reqs), 2, 'duplicate requestId counted once')


@case
def session_attributes_bust_to_model_switch():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p = transcript([assistant('r1', usage(read=10000, write_=100), 'claude-opus-5', t0),
                    assistant('r2', usage(read=50, write_=9000), 'claude-fable-5',
                              t0 + timedelta(minutes=1))])
    b = S.busts(S.scan(p)[0])
    eq(len(b), 1, 'one bust')
    assert 'model switch' in b[0]['cause'], b[0]['cause']


@case
def session_attributes_bust_to_ttl_expiry():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p = transcript([assistant('r1', usage(read=10000, write_=100), 'claude-opus-5', t0),
                    assistant('r2', usage(read=50, write_=9000), 'claude-opus-5',
                              t0 + timedelta(hours=3))])
    b = S.busts(S.scan(p)[0])
    eq(len(b), 1, 'one bust')
    assert 'TTL expiry' in b[0]['cause'], b[0]['cause']


@case
def session_no_bust_when_prefix_holds():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p = transcript([assistant('r1', usage(read=10000, write_=100), 'claude-opus-5', t0),
                    assistant('r2', usage(read=10100, write_=50), 'claude-opus-5',
                              t0 + timedelta(minutes=1))])
    eq(S.busts(S.scan(p)[0]), [], 'no bust when cache_read holds')


# ---------------------------------------------------------------- history.py

H = load('token-history', 'history.py')


@case
def history_baseline_is_the_cache_read_floor():
    p = transcript([assistant('r1', usage(read=24000, write_=100)),
                    assistant('r2', usage(read=31000, write_=100)),
                    assistant('r3', usage(read=28000, write_=100))])
    eq(H.scan_session(p)['baseline'], 24000, 'baseline is the minimum cache_read')


@case
def history_dedupes_by_request_id():
    p = transcript([assistant('r1', usage(read=100, out=5)),
                    assistant('r1', usage(read=100, out=5))])
    eq(H.scan_session(p)['requests'], 1, 'duplicate requestId counted once')


# --------------------------------------------------------------- overhead.py

O = load('token-overhead-audit', 'overhead.py')


@case
def overhead_dedupes_and_finds_baseline():
    p = transcript([assistant('r1', usage(read=24212, write_=10)),
                    assistant('r1', usage(read=24212, write_=10)),
                    assistant('r2', usage(read=30000, write_=10))])
    _comp, _pt, _hooks, floor, sessions, turns = O.scan([p])
    eq(floor, 24212, 'baseline floor')
    eq(turns, 2, 'duplicate requestId counted once')
    eq(sessions, 1, 'one session')


@case
def overhead_sizes_hook_and_skill_listing():
    recs = [assistant('r1', usage(read=100)),
            dict(type='attachment', attachment=dict(type='hook_success',
                                                    hookName='SessionStart:startup',
                                                    hookEvent='SessionStart',
                                                    durationMs=12, stdout='x' * 500)),
            dict(type='attachment', attachment=dict(type='skill_listing',
                                                    skillCount=7, content='y' * 300))]
    comp, _pt, hooks, _f, _s, _t = O.scan([transcript(recs)])
    eq(hooks[0]['chars'], 500, 'hook stdout sized')
    eq(comp['skill_listing']['detail'], 7, 'skillCount carried')


# ----------------------------------------------------------------- layout.py

LA = load('token-layout-audit', 'layout.py')


@case
def layout_parses_truncation_banner():
    banner = ('[Truncated: PARTIAL view — /a/b/digikamrc: showing lines 1-1648 of '
              '2264 total (29189 tokens, cap 25000). Call Read with offset=1649 …]')
    m = LA.TRUNC.search(banner)
    assert m, 'banner did not match'
    eq(m.groups(), ('/a/b/digikamrc', '2264', '29189', '25000'), 'banner fields')


@case
def layout_excludes_binary_by_extension():
    d = tmpdir()
    p = write(d, 'pic.png', 'not really a png but the extension decides')
    eq(LA.is_text(p), False, 'png excluded')


@case
def layout_excludes_binary_by_nul_sniff():
    d = tmpdir()
    p = os.path.join(d, 'blob.dat')
    with open(p, 'wb') as fh:
        fh.write(b'abc\0def')
    eq(LA.is_text(p), False, 'NUL content excluded')


@case
def layout_accepts_text():
    d = tmpdir()
    eq(LA.is_text(write(d, 'a.md', 'hello\n')), True, 'markdown accepted')


@case
def layout_finds_heavy_trees():
    d = tmpdir()
    write(d, 'node_modules/pkg/index.js', 'x\n')
    write(d, 'src/main.js', 'x\n')
    _files, _fan, heavy = LA.walk(d)
    assert 'node_modules' in heavy, heavy


# ------------------------------------------------------------------ index.py

IX = load('doc-index', 'index.py')


@case
def index_extracts_title_and_summary():
    d = tmpdir()
    p = write(d, 'a.md', '# Real Title\n\nFirst paragraph here.\n\n## Later\n\nIgnored.\n')
    title, summary, _size = IX.describe(p)
    eq(title, 'Real Title', 'title from H1')
    eq(summary, 'First paragraph here.', 'summary from first paragraph')


@case
def index_reports_unsummarised_document():
    d = tmpdir()
    p = write(d, 'a.md', '# Only A Heading\n\n## And Another\n')
    _t, summary, _s = IX.describe(p)
    eq(summary, '', 'no paragraph means no summary')


@case
def index_render_uses_relative_links():
    d = tmpdir()
    p = write(d, 'standards/a.md', '# T\n\nS.\n')
    out = IX.render(d, [(p, 'T', 'S.', 10)])
    assert '(standards/a.md)' in out, out


# ------------------------------------------------------------------ state.py

ST = load('session-handoff', 'state.py')


@case
def state_skips_shell_variable_assignments():
    tu = dict(type='tool_use', id='t1', name='Bash',
              input=dict(command="R='import json, sys' python3 -c 'x'"))
    p = transcript([assistant('r1', usage(read=10), content=[tu])])
    got = dict(ST.scan(p)['bash'])
    assert 'python3' in got, got
    assert not any(k.startswith('import') or k == 'json,' for k in got), got


@case
def state_records_written_files():
    tu = dict(type='tool_use', id='t1', name='Write', input=dict(file_path='/x/y.md'))
    p = transcript([assistant('r1', usage(read=10), content=[tu])])
    eq(list(ST.scan(p)['edited']), ['/x/y.md'], 'written file recorded')


# ------------------------------------------------------------------ bench.py

BE = load('token-benchmark', 'bench.py')


@case
def bench_overlap_detects_indistinguishable_arms():
    a = BE.summarise([100, 102, 104])
    b = BE.summarise([103, 105, 107])
    eq(BE.overlap(a, b), True, 'overlapping ranges')


@case
def bench_overlap_detects_separated_arms():
    a = BE.summarise([100, 101, 102])
    b = BE.summarise([200, 201, 202])
    eq(BE.overlap(a, b), False, 'separated ranges')


@case
def bench_summarise_reports_spread():
    s = BE.summarise([10, 20, 30])
    eq((s['n'], s['mean'], s['lo'], s['hi']), (3, 20, 10, 30), 'summary fields')


# --------------------------------------------------------------------- runner

def main():
    flt = sys.argv[1] if len(sys.argv) > 1 else ''
    picked = [c for c in CASES if flt in c.__name__]
    if not picked:
        print('no cases match %r' % flt)
        return 1
    failed = []
    for c in picked:
        try:
            c()
            print('  ok    %s' % c.__name__)
        except AssertionError as e:
            failed.append((c.__name__, str(e)))
            print('  FAIL  %s\n          %s' % (c.__name__, e))
        except Exception as e:
            failed.append((c.__name__, '%s: %s' % (type(e).__name__, e)))
            print('  ERROR %s\n          %s: %s' % (c.__name__, type(e).__name__, e))
    for d in TMPS:
        shutil.rmtree(d, ignore_errors=True)
    print('\n%d passed, %d failed, of %d' % (len(picked) - len(failed), len(failed), len(picked)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

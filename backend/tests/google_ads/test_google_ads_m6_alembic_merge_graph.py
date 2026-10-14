"""Assert M6 and main migrations join at a single head, without rewriting history."""
from pathlib import Path
import ast

from alembic.script import ScriptDirectory

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
FINAL = "c9e1a4d6b720"
EARLIER_JOIN = "a4c85d6e9f20"
TRACK_ROSTER = "f6roster1014"
MAIN = "c856map1014"
M6 = "d7f2a09c8b61"
BASE_M6 = "b3e7c2d9a104"
COMMON = "f62a1b9d4c07"


def test_m6_and_main_have_exactly_one_alembic_head():
    script = ScriptDirectory(str(MIGRATIONS))
    assert list(script.get_heads()) == [FINAL]
    join = script.get_revision(FINAL)
    assert set(join.down_revision) == {EARLIER_JOIN, TRACK_ROSTER}
    assert set(script.get_revision(EARLIER_JOIN).down_revision) == {MAIN, M6}
    assert script.get_revision(TRACK_ROSTER).down_revision == MAIN
    revisions = {r.revision for r in script.walk_revisions()}
    assert {MAIN, M6, BASE_M6, COMMON, EARLIER_JOIN, TRACK_ROSTER}.issubset(revisions)
    assert script.get_revision(M6).down_revision == BASE_M6
    assert script.get_revision(BASE_M6).down_revision == COMMON
    assert script.get_revision(MAIN).down_revision == "b856port1014"


def test_alembic_join_performs_no_ddl_dml_or_data_backfill():
    path = MIGRATIONS / "versions" / "c9e1a4d6b720_merge_m6_and_track_roster.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    functions = {
        n.name: n for n in module.body if isinstance(n, ast.FunctionDef)
    }
    assert set(functions) == {"upgrade", "downgrade"}
    for fn in functions.values():
        assert len(fn.body) == 1
        assert isinstance(fn.body[0], ast.Pass)

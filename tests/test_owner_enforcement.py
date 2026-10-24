"""Owner sayings carry an enforcement level (what makes the rule actually hold)."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from memkraft import MemKraft
from memkraft.owner_ledger import OwnerLedgerError


@pytest.fixture
def mk(tmp_path):
    store = MemKraft(base_dir=str(tmp_path / "mem"))
    store.owner_dir = tmp_path / "owner"
    return store


def test_new_saying_is_unclassified_until_classified(mk, tmp_path):
    a = mk.saying_record("다음 작업 목록이 모순이면 안 돼", scope="zeon")["id"]
    b = mk.saying_record("내 번호 기억해", scope="zeon")["id"]
    rep = mk.saying_enforcement_report()
    assert rep["unclassified"] == sorted([a, b]) and rep["ok"] is False
    (tmp_path / "upcoming.py").write_text("x")
    mk.saying_classify(a, "code", by=["upcoming.py"], note="kanban block")
    mk.saying_classify(b, "oneoff")
    rep = mk.saying_enforcement_report(root=tmp_path)
    assert rep["ok"] and rep["levels"] == {"code": 1, "oneoff": 1}


def test_enforced_level_requires_path_and_known_saying(mk):
    sid = mk.saying_record("멈추지 마", scope="all")["id"]
    with pytest.raises(OwnerLedgerError):
        mk.saying_classify(sid, "code")
    with pytest.raises(OwnerLedgerError):
        mk.saying_classify(sid, "maybe")
    with pytest.raises(OwnerLedgerError):
        mk.saying_classify("say-nope", "prose")


def test_vanished_enforcer_is_reported(mk, tmp_path):
    sid = mk.saying_record("반복 안 되게 고쳐", scope="all")["id"]
    f = tmp_path / "guard.py"
    f.write_text("x")
    mk.saying_classify(sid, "check", by=["guard.py"])
    assert mk.saying_enforcement_report(root=tmp_path)["ok"]
    f.unlink()
    rep = mk.saying_enforcement_report(root=tmp_path)
    assert rep["broken"] == [{"id": sid, "path": "guard.py"}] and not rep["ok"]


def test_latest_classification_wins_and_is_idempotent(mk):
    sid = mk.saying_record("알아서 끝까지 해", scope="all")["id"]
    assert mk.saying_classify(sid, "prose")["changed"] is True
    assert mk.saying_classify(sid, "prose")["changed"] is False
    mk.saying_classify(sid, "code", by=["a.py"])
    assert mk.saying_enforcement(sid)["level"] == "code"
    assert mk.saying_search("끝까지 알아서")[0]["enforcement"] == "code"
    rep = mk.saying_enforcement_report()
    assert rep["prose"] == [] and rep["levels"] == {"code": 1}


def test_retired_saying_leaves_report_and_text_never_in_report(mk):
    sid = mk.saying_record("번호 010-0000-0000 기억해", scope="zeon")["id"]
    assert "010-0000-0000" not in json.dumps(mk.saying_enforcement_report())
    mk.saying_retire(sid, "obsolete")
    assert mk.saying_enforcement_report()["total"] == 0


def test_sayings_file_stays_verbatim_only(mk):
    sid = mk.saying_record("규칙", scope="all")["id"]
    mk.saying_classify(sid, "prose")
    kinds = {json.loads(l)["kind"] for l in (mk.owner_dir / "sayings.jsonl").read_text().splitlines()}
    assert kinds == {"saying"}


def test_cli_enforcement_exit_code(mk, tmp_path):
    import os
    sid = mk.saying_record("규칙", scope="all")["id"]
    cli = [sys.executable, "-m", "memkraft.cli"]
    env = dict(os.environ, MEMKRAFT_DIR=str(tmp_path / "mem"), MEMKRAFT_OWNER_DIR=str(mk.owner_dir))
    r = subprocess.run(cli + ["owner", "enforcement"], capture_output=True, text=True, env=env)
    assert r.returncode == 1 and ("UNCLASSIFIED " + sid) in r.stdout
    r = subprocess.run(cli + ["owner", "classify", sid, "prose"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    r = subprocess.run(cli + ["owner", "enforcement"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "unclassified=0" in r.stdout

"""Hermes recall drops lessons that only share a particle or quoted prefix."""

import pytest


def _hp():
    pytest.importorskip("agent.memory_provider")
    from memkraft import hermes_provider

    return hermes_provider


def test_default_floor(monkeypatch):
    hp = _hp()
    monkeypatch.delenv("MEMKRAFT_HERMES_LESSON_MIN_SCORE", raising=False)
    assert hp._lesson_min_score() == pytest.approx(0.03)


@pytest.mark.parametrize("raw,want", [("0", 0.0), ("0.2", 0.2), ("-1", 0.0), ("bad", 0.03)])
def test_env_override(monkeypatch, raw, want):
    hp = _hp()
    monkeypatch.setenv("MEMKRAFT_HERMES_LESSON_MIN_SCORE", raw)
    assert hp._lesson_min_score() == pytest.approx(want)


def test_inject_passes_min_score(tmp_path):
    from memkraft import MemKraft

    mk = MemKraft(base_dir=str(tmp_path))
    calls = {}

    def fake(query, **kw):
        calls.update(kw)
        return ""

    mk.reasoning_inject_for_task = fake
    mk.development_inject_for_task("deploy wiki", style="full", min_score=0.03)
    assert calls["min_score"] == 0.03


def test_inject_default_keeps_old_behaviour(tmp_path):
    from memkraft import MemKraft

    mk = MemKraft(base_dir=str(tmp_path))
    calls = {}
    mk.reasoning_inject_for_task = lambda q, **kw: calls.update(kw) or ""
    mk.development_inject_for_task("deploy wiki")
    assert calls["min_score"] == 0.0

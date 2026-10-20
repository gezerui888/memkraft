"""Turn timing must not touch the delay ledger on the turn's hot path."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("agent.memory_provider")

from memkraft.hermes_provider import MemKraftMemoryProvider


def _provider(tmp_path: Path) -> MemKraftMemoryProvider:
    provider = MemKraftMemoryProvider()
    provider.initialize("session-private", hermes_home=str(tmp_path))
    return provider


def test_phase_transitions_do_not_write_the_ledger(tmp_path, monkeypatch):
    provider = _provider(tmp_path)
    store = provider._store
    calls = []
    monkeypatch.setattr(store, "delay_run_start", lambda *a, **k: calls.append("start"))
    monkeypatch.setattr(store, "delay_run_finish", lambda *a, **k: calls.append("finish"))

    provider.on_turn_timing_start(1, session_id="s", platform="telegram", subject="development")
    for i in range(50):
        provider.on_turn_progress(1, phase="wait", iteration=i)
        provider.on_turn_progress(1, phase="active", iteration=i)

    assert calls == []


def test_finished_turn_is_written_once_per_phase(tmp_path):
    provider = _provider(tmp_path)
    provider.on_turn_timing_start(1, session_id="s", platform="telegram", subject="development")
    for i in range(20):
        provider.on_turn_progress(1, phase="wait", iteration=i)
        provider.on_turn_progress(1, phase="active", iteration=i)
    provider.on_turn_progress(1, phase="rework", iteration=21)
    provider.on_turn_finish(1, outcome="completed")
    assert provider.flush_timing(timeout=30)

    ledger = (Path(provider._store.base_dir) / ".memkraft" / "delay" / "events.jsonl").read_text()
    lines = [line for line in ledger.splitlines() if line.strip()]
    # 1 task + 3 phase totals (active, rework, wait), each start + finish
    assert len(lines) == 8
    assert sum('"kind":"phase"' in line for line in lines) == 3


def test_shutdown_drains_queued_turns(tmp_path):
    provider = _provider(tmp_path)
    provider.on_turn_timing_start(1, session_id="s", platform="telegram", subject="ops")
    provider.on_turn_timing_start(2, session_id="s", platform="telegram", subject="ops")
    provider.on_turn_finish(1, outcome="completed")
    provider.shutdown()

    assert provider._timing_turns == {}
    assert provider.flush_timing(timeout=0)
    ledger = (Path(provider._store.base_dir) / ".memkraft" / "delay" / "events.jsonl").read_text()
    assert ledger.count('"record_type":"delay_run_finish"') >= 4

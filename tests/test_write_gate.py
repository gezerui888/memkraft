"""Write-time gate for automatic chat extraction (issue #19)."""

import json

import pytest

from memkraft import MemKraft
from memkraft import write_gate as wg

CHAT = "hermes:sess-1#assistant"
TEXT = "형, 해체 다음 지시는 끝났어. Run Time is great today. 비용은 78% 줄었고 $5M 남았다."


@pytest.fixture
def mk(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMKRAFT_WRITE_GATE", raising=False)
    m = MemKraft(base_dir=str(tmp_path / "mem"))
    m.init()
    return m


def _entity_files(mk):
    return sorted(p.name for p in mk.entities_dir.glob("*.md"))


def test_chat_extraction_creates_no_template_pages_and_logs_proposals(mk, capsys):
    mk.extract(TEXT, source=CHAT)
    assert _entity_files(mk) == []
    registry = mk.base_dir / "fact-registry.md"
    assert not registry.exists() or "78%" not in registry.read_text()
    log = [json.loads(l) for l in (mk.base_dir / ".memkraft" / "write-gate.jsonl").read_text().splitlines()]
    assert log and all(r["state"] == "proposed" and r["mode"] == "enforce" for r in log)
    assert {"entity", "registry"} <= {r["kind"] for r in log}


def test_explicit_source_keeps_historical_behaviour(mk, capsys):
    mk.extract(TEXT, source="meeting-notes.md")
    assert _entity_files(mk)
    assert not (mk.base_dir / ".memkraft" / "write-gate.jsonl").exists()


def test_preview_mode_writes_as_before_but_logs(mk, monkeypatch, capsys):
    monkeypatch.setenv("MEMKRAFT_WRITE_GATE", "preview")
    mk.extract(TEXT, source=CHAT)
    assert _entity_files(mk)
    log = (mk.base_dir / ".memkraft" / "write-gate.jsonl").read_text().splitlines()
    assert log and all(json.loads(l)["mode"] == "preview" for l in log)


def test_off_mode_disables_gate(mk, monkeypatch, capsys):
    monkeypatch.setenv("MEMKRAFT_WRITE_GATE", "off")
    mk.extract(TEXT, source=CHAT)
    assert _entity_files(mk)
    assert not (mk.base_dir / ".memkraft" / "write-gate.jsonl").exists()


def test_enriched_page_still_receives_chat_facts(mk, capsys):
    mk.extract("김민수는 개발자다.", source="manual")
    page = mk.entities_dir / f"{mk._slugify('김민수')}.md"
    assert page.exists()
    page.write_text(page.read_text().replace("(enrichment needed)", "Engineer")
                    .replace("Initial entity — enrichment needed", "met at kickoff"))
    mk.extract("김민수는 팀장이 되었다.", source=CHAT)
    assert "팀장" in page.read_text()


def test_template_page_is_not_retouched_by_chat(mk, capsys):
    mk.extract("박지성은 축구선수다.", source="manual")
    page = mk.entities_dir / f"{mk._slugify('박지성')}.md"
    before = page.read_text()
    mk.extract("박지성은 감독이 되었다.", source=CHAT)
    assert page.read_text() == before


def test_archive_is_dry_run_by_default_and_reversible(mk, capsys):
    mk.extract("이영희는 디자이너다.", source="manual")
    keep = mk.entities_dir / "keeper.md"
    keep.write_text("# Keeper\n\n## Timeline\n\n- **2026-10-20** | real fact [Source: manual]\n")
    before = _entity_files(mk)
    dry = wg.archive_noise_entities(mk.base_dir, mk.entities_dir)
    assert dry["candidates"] == len(before) - 1 and dry["applied"] is False
    assert _entity_files(mk) == before
    done = wg.archive_noise_entities(mk.base_dir, mk.entities_dir, apply=True)
    assert _entity_files(mk) == ["keeper.md"]
    back = wg.restore_archive(mk.base_dir, done["batch"])
    assert back["restored"] == done["moved"]
    assert _entity_files(mk) == before

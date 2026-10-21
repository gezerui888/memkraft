"""Recall must not spend its top-5 slots on copies or cron preambles."""
import pytest

pytest.importorskip("agent.memory_provider")

from memkraft.hermes_provider import MemKraftMemoryProvider, _diversify_hits

CRON = ("User: [IMPORTANT: You are running as a scheduled cron job. DELIVERY: Your final "
        "response will be automatically delivered]")


def _hit(file, snippet, score=1.0):
    return {"file": file, "snippet": snippet, "score": score}


def test_same_turn_artifact_and_live_note_collapse():
    hits = [
        _hit("artifacts/a.md", "Assistant: 형, 영어로 나간 보고는 미안해. 원인 찾아서 고쳤어."),
        _hit("live-notes/s-000002.md", "Assistant: 형, 영어로 나간 보고는 미안해. 원인 찾아서 고쳤어."),
        _hit("artifacts/b.md", "User: 클로드 키 사용량 얼만큼씩 남아있어?"),
    ]
    out = _diversify_hits(hits)
    assert [h["file"] for h in out] == ["artifacts/a.md", "artifacts/b.md"]


def test_json_wrapped_and_markdown_copies_collapse():
    hits = [
        _hit("artifacts/a.md", '{"content": "User: **왓츠앱** 매분 갱신 정상'),
        _hit("live-notes/x.md", "User: 왓츠앱 매분 갱신 정상"),
    ]
    assert len(_diversify_hits(hits)) == 1


def test_cron_preamble_dropped_but_kept_as_last_resort():
    hits = [_hit("artifacts/c%d.md" % i, CRON + " run %d" % i) for i in range(3)]
    assert _diversify_hits(hits) == []
    assert len(_diversify_hits(hits, keep_boilerplate=True)) >= 1


def test_distinct_hits_keep_relevance_order():
    hits = [_hit("f%d.md" % i, "distinct fact number %d about topic" % i) for i in range(6)]
    assert _diversify_hits(hits) == hits


class _Store:
    base_dir = "."

    def __init__(self, hits):
        self.hits = hits

    def search(self, query, top_k=12):
        return self.hits[:top_k]


def test_recall_hits_returns_five_distinct_from_polluted_store():
    polluted = [_hit("artifacts/c%d.md" % i, CRON + " %d" % i) for i in range(8)]
    polluted += [_hit("artifacts/d%d.md" % (i % 2), "same turn copy %d" % (i % 2)) for i in range(6)]
    polluted += [_hit("artifacts/u%d.md" % i, "useful memory %d" % i) for i in range(5)]
    p = MemKraftMemoryProvider()
    p._store = _Store(polluted)
    out = p._recall_hits("q", want=5)
    snippets = [h["snippet"] for h in out]
    assert len(out) == 5
    assert len(set(snippets)) == 5
    assert not any("scheduled cron job" in s for s in snippets)

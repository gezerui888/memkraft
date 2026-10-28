"""Auto-injected owner sayings stay within the active profile (plus scope=all)."""
import pytest

pytest.importorskip("agent.memory_provider")

from memkraft.hermes_provider import MemKraftMemoryProvider


@pytest.fixture(autouse=True)
def _iso(monkeypatch):
    for k in ("MEMKRAFT_DIR", "MEMKRAFT_OWNER_DIR", "MEMKRAFT_OWNER_SCOPE"):
        monkeypatch.delenv(k, raising=False)


def _provider(root, profile):
    home = root / "profiles" / profile
    home.mkdir(parents=True, exist_ok=True)
    p = MemKraftMemoryProvider()
    p.initialize("s-" + profile, hermes_home=str(home))
    return p


def _seed(root):
    w = _provider(root, "zeon")
    w._store.saying_record("배포 보고는 항상 표로 정리해", scope="zeon")
    w._store.saying_record("배포 보고는 짧게 한 줄로 해", scope="raon")
    w._store.saying_record("배포 보고에 비밀값은 절대 넣지마", scope="all")


def test_prefetch_hides_other_siblings_sayings(tmp_path):
    _seed(tmp_path)
    block = _provider(tmp_path, "zeon").prefetch("배포 보고 정리", session_id="s")
    assert "항상 표로" in block or "비밀값" in block
    assert "한 줄로" not in block
    raon = _provider(tmp_path, "raon").prefetch("배포 보고 정리", session_id="s")
    assert "항상 표로" not in raon


def test_scope_all_reaches_every_profile(tmp_path):
    _seed(tmp_path)
    block = _provider(tmp_path, "mion").prefetch("배포 보고 비밀값", session_id="s")
    assert "비밀값" in block and "표로" not in block and "한 줄로" not in block


def test_explicit_tool_search_still_sees_everything(tmp_path):
    _seed(tmp_path)
    store = _provider(tmp_path, "zeon")._store
    texts = {h["text"] for h in store.saying_search("배포 보고", limit=5)}
    assert any("한 줄로" in t for t in texts)


def test_env_override_scope(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("MEMKRAFT_OWNER_SCOPE", "raon")
    block = _provider(tmp_path, "zeon").prefetch("배포 보고 정리", session_id="s")
    assert "항상 표로" not in block

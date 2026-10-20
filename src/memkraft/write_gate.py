"""Write-time gate for automatic extraction (MAPLE-Guard style, rule based).

``extract()`` runs on every chat turn when MemKraft is a Hermes memory
provider.  Its regex NER turns Korean clause fragments (``해체``, ``다음``,
``시켰어``) and title-cased phrases (``Run Time``) into entity pages, and its
fact patterns copy sentence halves into ``fact-registry.md``.  Search already
hides those pages (:func:`is_stub_entity_text`), so they only cost disk,
cold-scan time and graph/conflict noise.  This module decides *before* the
write, with deterministic rules and no model call.

Policy (``MEMKRAFT_WRITE_GATE``):

* ``enforce`` (default) -- chat-sourced extraction may not create a new entity
  page, may not re-touch a page that is still an unenriched template, may not
  append facts to such a page, and may not register subject-less numbers.
  Rejected items are kept in ``.memkraft/write-gate.jsonl`` with state
  ``proposed`` so a curator can promote them later; nothing is lost.
* ``preview`` -- write exactly as before, but log what would be rejected.
* ``off`` -- no gate, no log.

Only sources that start with ``hermes:`` (automatic chat extraction) are
gated.  Explicit ``memkraft extract``/``track``/``update`` calls by a user or
agent with any other source keep the historical behaviour.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ._core_search_helpers import is_chat_derived_template_entity, is_stub_entity_text

CHAT_SOURCE_PREFIX = "hermes:"
_MODES = ("enforce", "preview", "off")


def gate_mode() -> str:
    mode = os.environ.get("MEMKRAFT_WRITE_GATE", "enforce").strip().lower()
    return mode if mode in _MODES else "enforce"


def is_chat_source(source: str) -> bool:
    return str(source or "").startswith(CHAT_SOURCE_PREFIX)


def _page_state(slug: str, dirs: Iterable[Optional[Path]], read: Callable[[Path], str]) -> str:
    """Return ``missing``, ``template`` or ``enriched`` for an entity slug."""
    for directory in dirs:
        if directory is None:
            continue
        path = directory / f"{slug}.md"
        if path.exists():
            text = read(path)
            if is_stub_entity_text(text) or is_chat_derived_template_entity(text):
                return "template"
            return "enriched"
    return "missing"


def judge_entity(slug: str, source: str, dirs: Iterable[Optional[Path]],
                 read: Callable[[Path], str]) -> Tuple[bool, str]:
    if not is_chat_source(source):
        return True, "explicit-source"
    state = _page_state(slug, dirs, read)
    if state == "enriched":
        return True, "enriched-page"
    if state == "template":
        return False, "template-page-redetect"
    return False, "chat-new-entity"


def judge_fact(slug: str, source: str, dirs: Iterable[Optional[Path]],
               read: Callable[[Path], str]) -> Tuple[bool, str]:
    if not is_chat_source(source):
        return True, "explicit-source"
    if _page_state(slug, dirs, read) == "enriched":
        return True, "enriched-page"
    return False, "fact-without-enriched-subject"


def judge_registry(entry: str, source: str) -> Tuple[bool, str]:
    """Bare regex captures (``78%``, ``$5M``, ``2026-10-20``) carry no subject."""
    if not is_chat_source(source):
        return True, "explicit-source"
    return False, "subjectless-number"


_LOG_MAX_BYTES = 5 * 1024 * 1024


def log_decisions(base_dir: Path, decisions: List[Dict[str, Any]]) -> None:
    if not decisions:
        return
    path = Path(base_dir) / ".memkraft" / "write-gate.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.stat().st_size > _LOG_MAX_BYTES:
            path.replace(path.with_suffix(".jsonl.1"))
    except FileNotFoundError:
        pass
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as fh:
        for d in decisions:
            fh.write(json.dumps(dict(d, at=stamp, state="proposed"), ensure_ascii=False) + "\n")


# ── One-off cleanup of pages written before the gate existed ─────────────

def archive_noise_entities(base_dir: Path, entities_dir: Path, *, apply: bool = False,
                           read: Optional[Callable[[Path], str]] = None) -> Dict[str, Any]:
    """Move template-only entity pages to ``.memkraft/archive/write-gate/<batch>``.

    Dry-run by default.  Pages are moved, never deleted, and a manifest is
    written so :func:`restore_archive` can put every file back.
    """
    read = read or (lambda p: p.read_text(encoding="utf-8", errors="replace"))
    picked: List[Path] = []
    for path in sorted(Path(entities_dir).glob("*.md")):
        text = read(path)
        if is_stub_entity_text(text) or is_chat_derived_template_entity(text):
            picked.append(path)
    result: Dict[str, Any] = {"candidates": len(picked), "applied": False}
    if not apply or not picked:
        return result
    batch = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = Path(base_dir) / ".memkraft" / "archive" / "write-gate" / batch
    (dest / "entities").mkdir(parents=True, exist_ok=True)
    moved = []
    for path in picked:
        target = dest / "entities" / path.name
        shutil.move(str(path), str(target))
        moved.append(path.name)
    (dest / "manifest.json").write_text(
        json.dumps({"batch": batch, "source_dir": str(entities_dir), "files": moved},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    result.update(applied=True, batch=batch, moved=len(moved), archive_dir=str(dest))
    return result


def restore_archive(base_dir: Path, batch: str) -> Dict[str, Any]:
    dest = Path(base_dir) / ".memkraft" / "archive" / "write-gate" / batch
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    source_dir = Path(manifest["source_dir"])
    restored, skipped = 0, 0
    for name in manifest["files"]:
        src = dest / "entities" / name
        target = source_dir / name
        if not src.exists() or target.exists():
            skipped += 1
            continue
        shutil.move(str(src), str(target))
        restored += 1
    return {"batch": batch, "restored": restored, "skipped": skipped}

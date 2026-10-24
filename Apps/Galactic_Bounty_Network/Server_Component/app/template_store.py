"""JSON-backed poster chrome template store with hunter/bounty seeds."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.models import DEFAULT_ACCENT, PosterTemplate, normalize_accent

_BUILTIN_SEEDS: List[PosterTemplate] = [
    PosterTemplate(
        id="hunter",
        name="Hunter",
        headline="GUN FOR HIRE",
        subtitle="",
        amount_label="RATE",
        list_label="REASONS TO HIRE",
        list_empty="Details pending",
        accent=DEFAULT_ACCENT,
        builtin=True,
    ),
    PosterTemplate(
        id="bounty",
        name="Bounty",
        headline="WANTED",
        subtitle="DEAD OR ALIVE",
        amount_label="REWARD",
        list_label="WANTED FOR",
        list_empty="Charges pending",
        accent=DEFAULT_ACCENT,
        builtin=True,
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    raw = (name or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "template"


class TemplateStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._seed_and_write()
        else:
            self._ensure_builtins()

    def _seed_and_write(self) -> None:
        stamp = _now()
        seeds = []
        for s in _BUILTIN_SEEDS:
            row = s.model_copy(deep=True)
            row.created_at = stamp
            row.updated_at = stamp
            seeds.append(row)
        self._write(seeds)

    def _read(self) -> List[PosterTemplate]:
        raw = self._path.read_text(encoding="utf-8")
        data = json.loads(raw or "[]")
        return [PosterTemplate.model_validate(item) for item in data]

    def _write(self, templates: List[PosterTemplate]) -> None:
        payload = [t.model_dump() for t in templates]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _ensure_builtins(self) -> None:
        with self._lock:
            templates = self._read()
            by_id = {t.id: t for t in templates}
            stamp = _now()
            changed = False
            for seed in _BUILTIN_SEEDS:
                if seed.id not in by_id:
                    row = seed.model_copy(deep=True)
                    row.created_at = stamp
                    row.updated_at = stamp
                    templates.append(row)
                    changed = True
            if changed:
                self._write(templates)

    def list(self) -> List[PosterTemplate]:
        with self._lock:
            templates = self._read()
            templates.sort(
                key=lambda t: (0 if t.builtin else 1, t.name.lower(), t.id)
            )
            return templates

    def get(self, template_id: str) -> Optional[PosterTemplate]:
        tid = (template_id or "").strip()
        if not tid:
            return None
        with self._lock:
            for t in self._read():
                if t.id == tid:
                    return t
            return None

    def builtin_for_role(self, role: str) -> PosterTemplate:
        tid = "hunter" if (role or "").strip().lower() == "hunter" else "bounty"
        found = self.get(tid)
        if found:
            return found
        # Extremely defensive — seeds should always exist
        for seed in _BUILTIN_SEEDS:
            if seed.id == tid:
                return seed
        return _BUILTIN_SEEDS[1]

    def save(self, template: PosterTemplate) -> PosterTemplate:
        with self._lock:
            templates = self._read()
            for i, existing in enumerate(templates):
                if existing.id == template.id:
                    if existing.builtin:
                        raise ValueError("Cannot overwrite a built-in template")
                    templates[i] = template
                    self._write(templates)
                    return template
            templates.append(template)
            self._write(templates)
            return template

    def create(
        self,
        *,
        name: str,
        headline: str,
        subtitle: str = "",
        amount_label: str = "REWARD",
        list_label: str = "WANTED FOR",
        list_empty: str = "Charges pending",
        accent: str = DEFAULT_ACCENT,
        template_id: str = "",
    ) -> PosterTemplate:
        stamp = _now()
        tid = (template_id or "").strip() or slugify(name)
        if tid in ("hunter", "bounty"):
            raise ValueError("Cannot create a template with a built-in id")
        with self._lock:
            templates = self._read()
            existing_ids = {t.id for t in templates}
            base = tid
            n = 2
            while tid in existing_ids:
                tid = f"{base}-{n}"
                n += 1
            row = PosterTemplate(
                id=tid,
                name=(name or tid).strip() or tid,
                headline=(headline or "").strip() or "WANTED",
                subtitle=(subtitle or "").strip(),
                amount_label=(amount_label or "").strip() or "REWARD",
                list_label=(list_label or "").strip() or "WANTED FOR",
                list_empty=(list_empty or "").strip() or "Charges pending",
                accent=normalize_accent(accent),
                builtin=False,
                created_at=stamp,
                updated_at=stamp,
            )
            templates.append(row)
            self._write(templates)
            return row

    def update(self, template_id: str, **fields) -> PosterTemplate:
        with self._lock:
            templates = self._read()
            for i, existing in enumerate(templates):
                if existing.id != template_id:
                    continue
                if existing.builtin:
                    raise ValueError("Cannot modify a built-in template")
                data = existing.model_dump()
                for key, value in fields.items():
                    if value is not None and key in data and key not in (
                        "id",
                        "builtin",
                        "created_at",
                    ):
                        data[key] = (
                            normalize_accent(value) if key == "accent" else value
                        )
                data["updated_at"] = _now()
                row = PosterTemplate.model_validate(data)
                templates[i] = row
                self._write(templates)
                return row
            raise KeyError(template_id)

    def delete(self, template_id: str) -> None:
        with self._lock:
            templates = self._read()
            for i, existing in enumerate(templates):
                if existing.id != template_id:
                    continue
                if existing.builtin:
                    raise ValueError("Cannot delete a built-in template")
                del templates[i]
                self._write(templates)
                return
            raise KeyError(template_id)

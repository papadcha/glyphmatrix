from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Family:
    id: int | None
    name: str
    foundry: str | None = None
    created_at: str | None = None


@dataclass
class FontFace:
    id: int | None
    family_id: int
    style: str | None = None
    weight: int | None = None
    width: str | None = None
    is_variable: bool = False
    axes: dict | None = None
    created_at: str | None = None


@dataclass
class FontFile:
    id: int | None
    font_face_id: int
    path: str
    filename: str
    format: str | None = None
    content_hash: str = ""
    hash_algorithm: str = "sha256"
    source: str = "user"
    version: str | None = None
    license: str | None = None
    glyph_count: int | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str | None = None


@dataclass
class Activation:
    id: int | None
    font_file_id: int
    platform: str | None = None
    state: str = "installed"
    activated_at: str | None = None
    deactivated_at: str | None = None


@dataclass
class FontGlyph:
    id: int | None
    font_file_id: int
    glyph_name: str
    unicode_codepoint: int | None = None
    contour_count: int | None = None
    advance_width: int | None = None
    outline_hash: str = ""


@dataclass
class ValidationIssue:
    id: int | None
    font_file_id: int
    severity: str
    issue_type: str
    detail: str | None = None
    detected_at: str | None = None
    resolved_at: str | None = None


@dataclass
class Tag:
    id: int | None
    name: str


@dataclass
class Collection:
    id: int | None
    name: str
    parent_id: int | None = None
    is_smart: bool = False
    smart_query: str | None = None


@dataclass
class ScanRun:
    id: int | None
    started_at: str | None = None
    finished_at: str | None = None
    files_scanned: int = 0
    files_added: int = 0
    files_changed: int = 0
    files_removed: int = 0
    errors: int = 0

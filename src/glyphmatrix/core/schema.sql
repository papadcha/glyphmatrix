-- GlyphMatrix font database schema v0.1
-- Frozen per docs/proposal.md Phase 0. Do not migrate without updating that doc.

CREATE TABLE IF NOT EXISTS families (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    foundry TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- A "face" is a logical style unit (e.g. "Bold"), independent of how many
-- physical files implement it (ttf + otf, static + variable, etc.)
CREATE TABLE IF NOT EXISTS font_faces (
    id INTEGER PRIMARY KEY,
    family_id INTEGER REFERENCES families(id),
    style TEXT,                 -- Regular, Medium, SemiBold, Bold, Italic...
    weight INTEGER,              -- 100-900
    width TEXT,
    is_variable INTEGER DEFAULT 0,
    axes_json TEXT,              -- e.g. {"wght":[100,900],"wdth":[75,125]} — schema forecast, no V0 logic
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- The actual file on disk. A face may have more than one file.
CREATE TABLE IF NOT EXISTS font_files (
    id INTEGER PRIMARY KEY,
    font_face_id INTEGER REFERENCES font_faces(id),
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    format TEXT,                 -- ttf, otf, woff2, ttc...
    content_hash TEXT NOT NULL,
    hash_algorithm TEXT DEFAULT 'sha256',
    source TEXT CHECK(source IN
        ('system','user','folder','google_fonts','project','imported')),
    version TEXT,
    license TEXT,
    glyph_count INTEGER,
    metadata_json TEXT,          -- safety valve for OpenType/other fields without migration
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Activation as a relation, not a file property — allows different state
-- per platform/project later without a schema change.
CREATE TABLE IF NOT EXISTS activations (
    id INTEGER PRIMARY KEY,
    font_file_id INTEGER REFERENCES font_files(id),
    platform TEXT,                -- windows/macos/linux — nullable, V0 is single-platform
    state TEXT CHECK(state IN ('available','installed','active','disabled'))
        DEFAULT 'installed',
    activated_at TEXT,
    deactivated_at TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE   -- "Sans"/"sans"/"SANS" = same tag
);

CREATE TABLE IF NOT EXISTS font_tags (
    font_face_id INTEGER REFERENCES font_faces(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (font_face_id, tag_id)
);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES collections(id),  -- hierarchical collections
    is_smart INTEGER DEFAULT 0,        -- no logic in V1 — schema forecast only
    smart_query TEXT                    -- activated in V2
);

CREATE TABLE IF NOT EXISTS collection_faces (
    collection_id INTEGER REFERENCES collections(id),
    font_face_id INTEGER REFERENCES font_faces(id),
    PRIMARY KEY (collection_id, font_face_id)
);

CREATE TABLE IF NOT EXISTS validation_issues (
    id INTEGER PRIMARY KEY,
    font_file_id INTEGER REFERENCES font_files(id),
    severity TEXT CHECK(severity IN ('info','warning','error')),
    issue_type TEXT,            -- corrupt, duplicate, missing_glyphs, license_conflict...
    detail TEXT,
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT             -- NULL = still active, avoids duplicate historical issues
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    files_scanned INTEGER,
    files_added INTEGER,
    files_changed INTEGER,
    files_removed INTEGER,
    errors INTEGER
);

# Font Manager — Project Proposal (v2)

Συγκεντρωτικό κείμενο από τρεις γύρους feedback (DeepSeek/ChatGPT/Gemini +
δεύτερη κριτική πάνω στο πρώτο draft) + δικές μου προσθήκες/αντιρρήσεις,
δομημένο με το ίδιο πνεύμα που ακολούθησε το **AiMusix**: μικρός, ξεκάθαρος
πυρήνας πρώτα, layered αρχιτεκτονική, τοπικό-first, μη-καταστροφικό.

## Product framing

Όχι απλά "Font Manager" — **Local Font Library & Activation Manager**.
Το differentiator δεν είναι η προβολή, είναι το πλήρες κύκλωμα:

```
Discover → Organize → Validate → Activate → Use
```

## Θεμελιώδεις αρχές (κλειδώνουν πριν τη βάση)

1. **Family intelligence από το V0** — `Inter-Regular.ttf`, `Inter-Bold.ttf` κ.λπ.
   δεν είναι ανεξάρτητα fonts· είναι styles μιας family. Επηρεάζει όλο το schema,
   πρέπει να αποφασιστεί πριν γραφτεί μία γραμμή SQL.
2. **Don't modify user files** — το filesystem είναι πάντα source of truth. Η
   βάση κρατάει `path`, `hash`, `metadata`, `activation_state` — ποτέ δεν
   μετακινεί/τροποποιεί το original αρχείο εκτός ρητού αιτήματος.
3. **Sources** — κάθε font έχει προέλευση (`system / user / folder / google_fonts /
   project / imported`). Χωρίς αυτό, δεν ξέρεις πού βρίσκεται το original όταν
   κάνεις deactivate, ούτε μπορείς να κάνεις σωστό Google Fonts import αργότερα.
4. **Layered architecture, GUI framework αποφασίζεται τελευταία**:

```
             ┌──────────────┐
             │     GUI      │   (Tauri/Electron — απόφαση αργότερα)
             └──────┬───────┘
                    │
             ┌──────▼───────┐
             │  Font Engine │   core/{scanner,parser,validator,duplicates,activation,renderer}
             └──────┬───────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     SQLite      System       Files
                  Fonts
```

## Θέση στην αγορά

Οι υπάρχοντες font managers χωρίζονται σε δύο στρατόπεδα:
- **Βαριά εργαλεία** (Suitcase Fusion, Extensis) — πλήρη αλλά αργά, enterprise-y.
- **Ελαφριά αλλά περιορισμένα** (Font Book, font-manager GTK) — γρήγορα αλλά χωρίς
  οργάνωση πέρα από system fonts.

Το κενό είναι ένα εργαλείο **γρήγορο, τοπικό, με πραγματική οργάνωση** (tags,
smart collections) χωρίς cloud/λογαριασμό — ακριβώς η θέση που πήρε το AiMusix
απέναντι σε Spotify-style βιβλιοθήκες.

## Activation model

Πιο πλούσιο από απλό installed/not-installed, αλλά **κλιμακούμενο**:

- **V0 (engine)**: 2 states — `Installed / Active`. Αρκεί για `fontctl activate`,
  `fontctl deactivate` να έχουν νόημα χωρίς sets/conflicts.
- **V1.5 (Activation Manager)**: επέκταση σε 4 states — `Available / Installed /
  Active / Disabled` — μαζί με **activation sets** (π.χ. project-based groups
  fonts που ενεργοποιούνται/απενεργοποιούνται μαζί), temporary activation,
  startup state restore, conflict handling.

Λόγος για τη σταδιακή προσέγγιση: αν μπουν 4 states + sets στο schema από το V0,
θα υπάρχουν CLI commands χωρίς πραγματική λογική πίσω τους. Το πεδίο στο schema
μπορεί να προβλέπεται, η λογική μπαίνει όταν χρειάζεται.

## Πυρήνας v1 — τι πρέπει να δουλεύει πρώτο

Από τις τρεις προτάσεις, αυτά είναι τα must-have που εμφανίζονται και στις τρεις
πηγές — άρα η ασφαλής βάση:

| Λειτουργία | Γιατί είναι core |
|---|---|
| **Scan & parse** (fontTools) | Χωρίς σωστό parsing metadata, τίποτα άλλο δεν χτίζεται πάνω. |
| **On-demand activation/deactivation** | Είναι ο λόγος ύπαρξης ενός font manager — διαφορετικά είναι απλώς file browser. |
| **Duplicate & corruption detection** | Ίδιο μοτίβο με το `validation` του AiMusix — offline, χωρίς εξωτερικές εξαρτήσεις. |
| **Version & Glyph Comparison** | Πραγματική ανάγκη χρήστη: ίδια family/style, διαφορετικό `version` (π.χ. Arial v1 vs v4) μπορεί να έχει διαφορετικό glyph coverage *και* διαφορετικό outline στο ίδιο glyph name. Ξεχωριστό feature από το duplicate detection — βλ. ενότητα παρακάτω. |
| **Preview (waterfall + custom text)** | Το πρώτο πράγμα που θα δοκιμάσει κάθε χρήστης. |
| **Tags + Collections (χωρίς "smart" ακόμα)** | Οργάνωση πριν την αναζήτηση — η αναζήτηση δεν έχει νόημα σε άδεια βιβλιοθήκη. |
| **Τοπική SQLite βάση** | Ίδιο σχήμα σκέψης με AiMusix: `fonts`, `families`, `activations`, `validation_issues`. |

Όλα τα υπόλοιπα (glyph inspector, license tracking, Google Fonts, AI tagging,
font pairing, visual matcher) πάνε **μετά** — είναι πραγματικά καλές ιδέες, αλλά
αν μπουν στο v1 θα καθυστερήσουν κάτι που παίζει.

## Version & Glyph Comparison (προστέθηκε μετά από feedback χρήστη)

Ο βασικός λόγος ύπαρξης του εργαλείου για τον χρήστη δεν είναι μόνο "βρες
duplicates", είναι **σύγκριση εκδόσεων της ίδιας family/style**: π.χ. Arial
version 1 έχει διαφορετικό outline στο glyph "δ" απ' ό,τι η version 4, η οποία
επιπλέον έχει περισσότερα glyphs συνολικά.

Αυτό είναι εννοιολογικά διαφορετικό από το duplicate detection:

- **Duplicate detection** (`content_hash` στο `font_files`) πιάνει μόνο
  *byte-identical* αρχεία — χρήσιμο για "έχω δύο αντίγραφα του ίδιου ακριβώς
  αρχείου σε διαφορετικούς φακέλους".
- **Version comparison** χρειάζεται σύγκριση σε επίπεδο glyph ανάμεσα σε δύο
  `font_files` που ανήκουν στο **ίδιο** `font_face` (ίδια family+style) αλλά
  διαφορετικό `version` — ποια glyphs υπάρχουν μόνο στη μία έκδοση, ποια
  υπάρχουν και στις δύο αλλά άλλαξε το outline τους.

Για να είναι αυτό φθηνό να υπολογιστεί (χωρίς re-parse του font κάθε φορά),
το scan αποθηκεύει ένα **per-glyph fingerprint** ανά `font_file` (νέος πίνακας
`font_glyphs` — βλ. schema): glyph name, unicode codepoint, contour count,
advance width, και ένα `outline_hash` (hash πάνω στα σημεία του contour, όχι
απλά rendered pixels — πιάνει αλλαγές στο σχήμα ακόμα κι αν είναι οπτικά
μικρές).

Η ίδια η σύγκριση είναι τότε ένα απλό set-diff πάνω στο `font_glyphs`:

```
μόνο στην A       = glyphs(A) − glyphs(B)
μόνο στην B       = glyphs(B) − glyphs(A)
ίδιο glyph_name,
διαφορετικό
outline_hash      = άλλαξε το σχήμα του glyph ανάμεσα στις εκδόσεις
```

Προτεινόμενο νέο command (V1, όχι μέσα στα "παγωμένα" 7 του V0 engine):

```
fontctl compare <family> <style> <version_a> <version_b>
```

## Packages & Documentation (προστέθηκε μετά από feedback χρήστη, 2026-08-10)

Ο χρήστης έχει παλιά πακέτα fonts (π.χ. Adobe Font Folio) — δεν θέλει
απαραίτητα να κρατήσει τα ίδια τα fonts, αλλά του αρέσει η ιδέα να
σημειώνεται **από ποιο πακέτο ήρθε** κάθε αρχείο, και κάποια πακέτα έχουν
δικά τους συνοδευτικά έγγραφα (license PDF, README).

Αυτό είναι εννοιολογικά διαφορετικό από `collections`:

- **Collection** = υποκειμενική οργάνωση του χρήστη (π.χ. "Body Text
  Fonts") — τίποτα να κάνει με το πώς αποκτήθηκε το font.
- **Package** = γεγονός προέλευσης — "αυτό το αρχείο ήρθε μέσα σε αυτό το
  distribution bundle", με δικά του metadata (vendor, σημειώσεις) και
  προαιρετικά συνοδευτικά έγγραφα.

Νέος πίνακας `packages` (name UNIQUE, vendor, notes) + junction
`package_files` (σε επίπεδο `font_files`, όχι `font_faces` — ένα πακέτο
αφορά συγκεκριμένα φυσικά αρχεία, ίδιο επίπεδο granularity με το `source`)
+ `package_documents` (path + description, ίδια αρχή "ποτέ δεν
αντιγράφουμε/αγγίζουμε" όπως και τα font paths).

```
fontctl package create <name> [--vendor] [--notes]
fontctl package add <package> <family> <style>
fontctl package remove <package> <family> <style>
fontctl package list
fontctl package show <package>
fontctl package doc-add <package> <path> [--description]
fontctl package doc-remove <package> <path>
```

## Η δική μου κρίση πάνω στις προτάσεις

- **Συμφωνώ** με το activation-on-demand ως κεντρικό feature — είναι αυτό που
  κάνει ένα font manager χρήσιμο έναντι απλής σάρωσης φακέλου.
- **Θα απέφευγα** το "AI Auto-Tagging / Mood Classification" (Cyberpunk, 80s
  Synthwave κ.λπ.) στο v1. Χρειάζεται είτε τοπικό μοντέλο (CLIP/ONNX) είτε API
  call, και είναι υποκειμενικό — καλύτερα να αφήσεις τον χρήστη να βάλει tags
  πρώτα και να δεις τι πραγματικά θέλει να φιλτράρει, πριν επενδύσεις σε AI εκεί.
- **Visual Matcher (image-to-font)** είναι εντυπωσιακό αλλά δύσκολο να βγει καλό
  χωρίς μεγάλο dataset αναφοράς — θα το έβαζα στο "ίσως ποτέ", όχι στο roadmap.
- **Text-to-Font Search σε φυσική γλώσσα** είναι εφικτό *φθηνά* αν βασιστεί απλώς
  σε καλά structured tags + μια απλή query γλώσσα (Quod Libet style, όπως στο
  AiMusix roadmap) αντί για πραγματικό NLP model. Ίδιο αποτέλεσμα, μηδενικό
  κόστος συντήρησης.
- **Font Pairing Engine**: καλή ιδέα για *μετά* το activation system, γιατί
  χρειάζεται ήδη οργανωμένη βιβλιοθήκη με tags για να έχει νόημα η πρόταση.
- Τα **AiMusix-specific εξειδικευμένα features** (album art presets, export σε
  SVG/PNG) είναι πολύ συγκεκριμένα — τα κρατάω σαν *integration layer* πάνω από
  τον γενικό font manager, όχι μέσα στον πυρήνα του. Έτσι το εργαλείο μένει
  χρήσιμο και standalone.

## Tech stack — πρόταση

Ακολουθώντας τη λογική του AiMusix (Python core, CLI πρώτα):

- **Core / parsing**: Python + `fontTools` — ώριμη, ίδια γλώσσα με το AiMusix άρα
  reusable γνώση/κώδικας (π.χ. validation patterns).
- **Storage**: SQLite, ίδιο σχήμα σκέψης με AiMusix.
- **CLI πρώτα**: `fontctl scan`, `fontctl list`, `fontctl activate <family>`,
  `fontctl issues`, `fontctl preview <family> --text "..."` (εξάγει PNG/SVG).
- **GUI αργότερα**: αν χρειαστεί, **Tauri** (Rust shell + web frontend) αντί για
  Electron — πολύ πιο ελαφρύ footprint, σημαντικό για εργαλείο που θα τρέχει
  συνέχεια στο background για activation. Electron είναι αποδεκτό fallback αν
  θέλεις ταχύτερο MVP.
- **Font rendering σε preview**: Canvas/WebGL μόνο όταν υπάρχει GUI· στο CLI
  στάδιο αρκεί raster export μέσω `fontTools` + Pillow, όπως έκανες preview PNGs
  στο AiMusix branding.

## Πλατφόρμα

Ερώτημα ανοιχτό — αλλά μια σκέψη: αν το activation πρέπει να αγγίζει πραγματικά
system font directories, macOS/Windows/Linux έχουν τελείως διαφορετικά APIs για
αυτό. Προτείνω να ξεκινήσεις με **μία πλατφόρμα** (ό,τι χρησιμοποιείς εσύ καθημερινά)
και να αφήσεις cross-platform activation για το phase 2 — είναι το κομμάτι που
θα σε καθυστερήσει περισσότερο αν το κυνηγήσεις νωρίς.

## Roadmap (αναθεωρημένο — πιο σταδιακό)

**V0 — Font Engine** (πριν καν GUI)
```
fontctl scan
fontctl list
fontctl info <family>
fontctl validate
fontctl duplicates
fontctl activate / deactivate
```
Αυτό είναι απλά ο μηχανισμός· δεν έχει ακόμα "προϊόν" γύρω του.

**V1 — Font Library**
SQLite, families, styles, tags, collections, search, preview, favorites,
validation status, **`fontctl compare`** (version & glyph comparison — βλ.
ενότητα "Version & Glyph Comparison" παραπάνω). Εδώ γίνεται πραγματικά
χρησιμοποιήσιμη βιβλιοθήκη.

**V1.5 — Activation Manager**
Activation sets, temporary activation, startup state, restore previous state,
conflict handling. Εδώ γίνεται πραγματικά **Font Manager**, όχι απλός viewer.

**V2 — Intelligence**
Smart collections (query language πάνω στα tags/metadata, π.χ.
`license=commercial AND style=serif`), license metadata, glyph inspector,
language coverage, OpenType features, font pairing.

**V3 — Ecosystem**
Google Fonts integration, PDF κατάλογος, auto-activation ανά document/project,
integrations — προαιρετικά AiMusix integration μέσω API/CLI, όχι tight coupling.

**V4 — Πειραματικό / ίσως ποτέ**
AI mood tagging, visual/image-to-font matcher, cloud/team sync.

## SQLite schema v0.1 (frozen foundation, μετά από 3 γύρους review)

Διόρθωσε δύο συγχύσεις του πρώτου draft: **file ≠ face ≠ family**, και
**source ≠ activation state**. Ο εμπλουτισμός του schema **δεν** σημαίνει
εμπλουτισμό του V0 CLI scope — τα 7 `fontctl` commands μένουν ίδια, το schema
απλά δεν χρειάζεται migration όταν προστεθούν variable fonts ή project-based
activation.

```sql
CREATE TABLE families (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    foundry TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Ένα "face" = μια λογική στυλιστική μονάδα (π.χ. "Bold"), ανεξάρτητη
-- από το πόσα φυσικά αρχεία την υλοποιούν (ttf + otf, static + variable κ.λπ.)
CREATE TABLE font_faces (
    id INTEGER PRIMARY KEY,
    family_id INTEGER REFERENCES families(id),
    style TEXT,                 -- Regular, Medium, SemiBold, Bold, Italic...
    weight INTEGER,              -- 100-900
    width TEXT,
    is_variable INTEGER DEFAULT 0,
    axes_json TEXT,              -- π.χ. {"wght":[100,900],"wdth":[75,125]} — πρόβλεψη, όχι V0 λογική
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Το πραγματικό αρχείο στο δίσκο. Ένα face μπορεί να έχει πάνω από ένα file.
CREATE TABLE font_files (
    id INTEGER PRIMARY KEY,
    font_face_id INTEGER REFERENCES font_faces(id),
    path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    format TEXT,                 -- ttf, otf, woff2, ttc...
    content_hash TEXT NOT NULL,
    hash_algorithm TEXT DEFAULT 'sha256',
    source TEXT CHECK(source IN
        ('system','user','folder','google_fonts','project','imported')),
    version TEXT,
    license TEXT,
    glyph_count INTEGER,
    metadata_json TEXT,          -- safety valve για OpenType/άλλα fields χωρίς migration
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_font_files_content_hash ON font_files(content_hash);

-- Activation ως σχέση, όχι ιδιότητα του αρχείου — επιτρέπει
-- διαφορετικό state ανά platform/project στο μέλλον χωρίς αλλαγή σχήματος.
CREATE TABLE activations (
    id INTEGER PRIMARY KEY,
    font_file_id INTEGER REFERENCES font_files(id),
    platform TEXT,                -- windows/macos/linux — nullable, V0 έχει μία πλατφόρμα
    state TEXT CHECK(state IN ('available','installed','active','disabled'))
        DEFAULT 'installed',
    activated_at TEXT,
    deactivated_at TEXT,
    UNIQUE(font_file_id, platform)
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE   -- "Sans"/"sans"/"SANS" = ίδιο tag
);

CREATE TABLE font_tags (
    font_face_id INTEGER REFERENCES font_faces(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (font_face_id, tag_id)
);

CREATE TABLE collections (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    parent_id INTEGER REFERENCES collections(id),  -- ιεραρχικές συλλογές
    is_smart INTEGER DEFAULT 0,        -- χωρίς λογική στο V1 — μόνο πρόβλεψη σχήματος
    smart_query TEXT                    -- ενεργοποιείται στο V2
);

CREATE TABLE collection_faces (
    collection_id INTEGER REFERENCES collections(id),
    font_face_id INTEGER REFERENCES font_faces(id),
    PRIMARY KEY (collection_id, font_face_id)
);

-- Πραγματικό distribution bundle (π.χ. "Adobe Font Folio 11") — προέλευση,
-- όχι υποκειμενική οργάνωση. Membership σε επίπεδο font_file (όχι
-- font_face), ίδιο granularity με το font_files.source. Βλ. ενότητα
-- "Packages & Documentation".
CREATE TABLE packages (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    vendor TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE package_files (
    package_id INTEGER REFERENCES packages(id),
    font_file_id INTEGER REFERENCES font_files(id),
    PRIMARY KEY (package_id, font_file_id)
);

-- Έγγραφα που ήρθαν μαζί με το πακέτο (PDF license, readme) — μόνο path,
-- ίδια αρχή μη-καταστροφικότητας με το font_files.path.
CREATE TABLE package_documents (
    id INTEGER PRIMARY KEY,
    package_id INTEGER REFERENCES packages(id),
    path TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Per-glyph fingerprint, μία γραμμή ανά glyph ανά font_file. Επιτρέπει σύγκριση
-- glyph coverage/outline ανάμεσα σε εκδόσεις του ίδιου font_face χωρίς re-parse
-- κάθε φορά — βλ. ενότητα "Version & Glyph Comparison".
CREATE TABLE font_glyphs (
    id INTEGER PRIMARY KEY,
    font_file_id INTEGER REFERENCES font_files(id),
    glyph_name TEXT NOT NULL,
    unicode_codepoint INTEGER,
    contour_count INTEGER,
    advance_width INTEGER,
    outline_hash TEXT NOT NULL,   -- hash πάνω στα σημεία του contour, όχι rendered pixels
    UNIQUE(font_file_id, glyph_name)
);

CREATE INDEX idx_font_glyphs_file ON font_glyphs(font_file_id);
CREATE INDEX idx_font_glyphs_name ON font_glyphs(glyph_name);

CREATE TABLE validation_issues (
    id INTEGER PRIMARY KEY,
    font_file_id INTEGER REFERENCES font_files(id),
    severity TEXT CHECK(severity IN ('info','warning','error')),
    issue_type TEXT,            -- corrupt, duplicate, missing_glyphs, license_conflict...
    detail TEXT,
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT             -- NULL = ακόμα ενεργό· αποφεύγει duplicate ιστορικά issues
);

CREATE TABLE scan_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    files_scanned INTEGER,
    files_added INTEGER,
    files_changed INTEGER,
    files_removed INTEGER,
    errors INTEGER
);
```

Conceptual σχήμα:

```
families → font_faces → font_files
                              │
                ┌─────────────┼─────────────┬──────────────┬─────────────┐
                ▼             ▼             ▼              ▼             ▼
          activations   validation_issues  metadata_json  font_glyphs  package_files
                                                            (compare εκδόσεις  │
                                                             εντός font_face)  ▼
                                                                            packages ── package_documents

font_tags ── tags          collection_faces ── collections
scan_runs (ανεξάρτητο, καταγράφει κάθε scan)
```

## Platform abstraction (αυστηρός κανόνας)

Core **δεν** πρέπει να ξέρει ότι υπάρχει Windows/macOS/Linux:

```
core/
    scanner.py
    parser.py
    validator.py
    database.py
    models.py
    ...

platforms/                     # plural — "platform" alone shadows the stdlib module
    windows.py
    macos.py
    linux.py
```

(Διαφέρει ελαφρώς από το αρχικό σχέδιο παραπάνω — flat modules αντί για nested
φακέλους ανά OS, ίδια ιδέα.)

Interface: `ActivationProvider` — το core καλεί το interface, όχι συγκεκριμένο
platform module. Έτσι το πρώτο platform port είναι *extension*, όχι rewrite.

## Phase 0 — Architecture Freeze (πριν οποιονδήποτε κώδικα GUI/HTML)

1. Domain model (families/font_faces/font_files/activations — παραπάνω)
2. SQLite schema v0.1 (παραπάνω — pending τελικό review)
3. Platform abstraction (`ActivationProvider` interface)
4. Activation contract (ποιες μεταβάσεις states επιτρέπονται, τι σημαίνει καθεμία)
5. `fontctl` command contract (ακριβή flags, ακριβές output format — JSON; ή plain text;)
6. Directory structure (`core/`, `platform/`, `cli/`, `database/`, `tests/`, `docs/`)
7. Tests πάνω σε όλα τα παραπάνω

Μόνο μετά από αυτό το review, γράφεται ο πρώτος πραγματικός κώδικας.

## Έμπνευση

- **RightFont / FontBase** — το activation-on-demand μοντέλο ως πρότυπο.
- **font-manager (GTK)** — ελαφρύ, open-source σημείο αναφοράς για parsing.
- **fontastic** — ιδέες για ιεραρχικές/smart collections.
- **Quod Libet** (ήδη έμπνευση στο AiMusix) — η query γλώσσα μεταφέρεται ιδανικά
  και σε fonts.

## GUI concept (σημείωση για αργότερα, όχι απόφαση τώρα)

Ιδέα που αξίζει να κρατηθεί: αντί για κλασικό sidebar + λίστα + properties
panel, ένα **Font Canvas / Library view** — μεγάλα specimen blocks ανά family με
inline style switcher, click → full-page workspace. Δεν επηρεάζει schema/CLI,
οπότε δεν χρειάζεται απόφαση τώρα — μπαίνει στο V1.5+ όταν αποφασιστεί το GUI
framework.

## Standalone, όχι tight-coupled με AiMusix

Ο Font Manager χτίζεται και δουλεύει **ανεξάρτητα** από το AiMusix. Integration
μόνο μέσω API/CLI αργότερα:

```
AiMusix ──(Font API / CLI)──▶ Font Manager
```

Το AiMusix μπορεί αργότερα να προσθέσει ένα "Manage Fonts" που καλεί τον Font
Manager, αλλά ο Font Manager δεν χρειάζεται ποτέ το AiMusix για να λειτουργήσει.

## Επόμενο βήμα (πριν οποιαδήποτε γραμμή GUI/HTML)

Κλείδωμα, με αυτή τη σειρά:
1. Architecture (το layered διάγραμμα παραπάνω)
2. SQLite schema (το draft παραπάνω — χρειάζεται review/iteration)
3. Activation model (2-state V0 → 4-state + sets στο V1.5)
4. CLI contract (ακριβή commands, flags, output format του `fontctl`)

Μόνο μετά αποφασίζεται GUI framework.

## Ανοιχτές αποφάσεις

1. **Πλατφόρμα εκκίνησης** — **κλειδώθηκε: macOS-first**. Σε προηγούμενα
   feedback rounds (DeepSeek/ChatGPT/Gemini) η πρόταση ήταν πάντα macOS ή
   Linux· επιβεβαιώθηκε macOS. `platforms/macos.py` ήταν η πρώτη πραγματική
   `ActivationProvider` υλοποίηση (symlink σε `~/Library/Fonts`)· ακολούθησε
   `platforms/windows.py` (2026-08-11, `AddFontResourceEx`/`RemoveFontResourceEx`
   μέσω ctypes, verified σε πραγματικό hardware)· `platforms/linux.py`
   (2026-08-11, symlink σε `~/.local/share/fonts` + `fc-cache`, ίδιο μοτίβο
   με macOS) — και τα τρία `ActivationProvider` υλοποιημένα πλέον, το Linux
   μόνο unit-tested με mocked `fc-cache`, όχι ακόμα σε πραγματικό hardware.
2. Desktop framework για το GUI, όταν φτάσουμε εκεί (Tauri vs Electron) — **όχι
   τώρα**, μετά το V1.5.
3. **Κλειδώθηκε: standalone.** Ξεχωριστό εργαλείο/repo, όχι module μέσα στο
   AiMusix — επιβεβαιώθηκε ρητά. Integration μόνο μέσω API/CLI αργότερα, βλ.
   ενότητα "Standalone, όχι tight-coupled με AiMusix".
4. **Κλειδώθηκε (2026-08-10, μετά από πραγματική χρήση όλων των modules):**
   βρέθηκαν και διορθώθηκαν 3 πραγματικά κενά — `families.foundry` υπήρχε
   αλλά ποτέ δεν γέμιζε (τώρα εξάγεται από nameID 8 "Manufacturer"), έλειπαν
   indexes σε `font_files.path`/`content_hash`, και τρία UNIQUE constraints
   (`font_files.path`, `activations(font_file_id, platform)`,
   `collections.name`) επιβάλλονταν μόνο σε επίπεδο εφαρμογής χωρίς DB
   guarantee. Ό,τι άλλο φαινόταν "άδειο" (`axes_json`, `is_smart`/
   `smart_query`, `metadata_json`) είναι σκόπιμο schema forecast, όχι κενό.
5. **Κλειδώθηκε: και τα δύο.** Plain text default, `--json` flag για
   scriptability — ήδη έτσι υλοποιημένο σε κάθε command, επιβεβαιώθηκε ρητά.

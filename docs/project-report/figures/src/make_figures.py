"""Generates the SVG figures of the AI Career Companion academic project report.

Every diagram is drawn from facts verified in the repository (module names, tables,
endpoints, constants). Canvases are about 900 px wide with 14-17 px text so that, at the
report's 5.77-inch text width, printed text is roughly 6.5-8 pt. The ERD is drawn wider
and placed rotated on its own page. Run from the repository root:

    .venv\\Scripts\\python.exe docs\\project-report\\figures\\src\\make_figures.py

SVG files are written to docs/project-report/figures/. PNG renders are produced by
render_figures.ps1 (headless Chrome) for embedding in the DOCX/PDF.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]

INK = "#1d2733"
MUTED = "#4a5563"
LINE = "#4a5868"
NAVY = "#1f3a5f"
FILL = "#eef3f9"
FILL2 = "#f7f9fb"
STORE = "#f3f0e8"
STORE_LINE = "#8a7a55"
OPT = "#fbf3ea"
OPT_LINE = "#b5651d"
GREY_FILL = "#f1f1f1"
GREY_LINE = "#8f98a3"
WARN_FILL = "#fff8e5"
WARN_LINE = "#b08d2e"
FONT = "Segoe UI, Arial, Helvetica, sans-serif"
MONO = "Consolas, 'Courier New', monospace"

T, B, N = 17, 15, 14  # title, body and note text sizes (px)


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.w, self.h = width, height
        self.parts: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, size=B, weight="normal", anchor="middle", color=INK, family=FONT, italic=False):
        style = ' font-style="italic"' if italic else ""
        self.add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
                 f'text-anchor="{anchor}" fill="{color}"{style}>{escape(s)}</text>')

    def lines(self, x, y, items, size=N, anchor="middle", color=MUTED, italic=False, gap=None):
        for k, s in enumerate(items):
            self.text(x, y + k * (gap or size + 5), s, size=size, anchor=anchor, color=color, italic=italic)

    def box(self, x, y, w, h, lines, fill=FILL, stroke=NAVY, title_size=T, size=B, dashed=False, rx=7,
            stroke_width=1.6, title_color=INK):
        dash = ' stroke-dasharray="7 4"' if dashed else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="{stroke_width}"{dash}/>')
        if not lines:
            return
        line_h = size + 5
        total = title_size + (len(lines) - 1) * line_h + (4 if len(lines) > 1 else 0)
        cy = y + h / 2 - total / 2 + title_size * 0.8
        self.text(x + w / 2, cy, lines[0], size=title_size, weight="bold", color=title_color)
        cy += 4
        for line in lines[1:]:
            cy += line_h
            self.text(x + w / 2, cy, line, size=size, color=MUTED)

    def boundary(self, x, y, w, h, label, color=GREY_LINE):
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{color}" '
                 f'stroke-width="1.6" stroke-dasharray="9 5"/>')
        self.text(x + 12, y + 21, label, size=N, weight="bold", anchor="start", color=color)

    def arrow(self, pts, label=None, dashed=False, color=LINE, label_pos=None, label_anchor="middle",
              both=False, size=N, width=1.6):
        d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
        dash = ' stroke-dasharray="7 4"' if dashed else ""
        mid = "arr" if color == LINE else "arro"
        start = f' marker-start="url(#{mid})"' if both else ""
        self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
                 f'marker-end="url(#{mid})"{start}/>')
        if label:
            lx, ly = label_pos
            tw = len(label) * size * 0.56 + 10
            bx = lx - tw / 2 if label_anchor == "middle" else (lx - 5 if label_anchor == "start" else lx - tw + 5)
            self.add(f'<rect x="{bx:.1f}" y="{ly - size}" width="{tw:.1f}" height="{size + 6}" fill="white" opacity="0.92"/>')
            self.text(lx, ly, label, size=size, anchor=label_anchor, color=MUTED if color == LINE else color)

    def line(self, x1, y1, x2, y2, color=LINE, dashed=False, width=1.6):
        dash = ' stroke-dasharray="7 4"' if dashed else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{dash}/>')

    def render(self) -> str:
        def marker(mid, fill):
            return (f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
                    f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{fill}"/></marker>')
        defs = "<defs>" + marker("arr", LINE) + marker("arro", OPT_LINE) + "</defs>"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}">{defs}<rect width="100%" height="100%" fill="white"/>'
                + "".join(self.parts) + "</svg>\n")


def save(name: str, svg: Svg) -> None:
    (OUT / f"{name}.svg").write_text(svg.render(), encoding="utf-8")
    print("wrote", name)


# ---------------------------------------------------------------------------
# Figure 4.1 — logical architecture
# ---------------------------------------------------------------------------
def architecture() -> None:
    s = Svg(900, 1190)
    s.boundary(15, 10, 870, 125, "CLIENT TIER (browser)")
    s.box(35, 45, 170, 72, ["Student", "web browser"], fill=FILL2)
    s.box(245, 40, 620, 82, ["React 19 + TypeScript SPA (Vite 6)", "views · typed API clients · apiFetch"])
    s.arrow([(205, 81), (243, 81)])

    s.boundary(15, 172, 870, 128, "API TIER (backend/app/main.py)")
    s.box(35, 203, 830, 84, ["FastAPI application — 11 routers",
                             "Pydantic validation · CORS · JSON error handler",
                             "require_current_user · ownership checks"])
    s.arrow([(555, 122), (555, 201)], both=True, label="JSON over HTTP + session cookie", label_pos=(555, 158))

    s.boundary(15, 335, 605, 515, "SERVICE TIER (deterministic core)")
    names = [["Resume pipeline", "parse → structure → context"], ["Semantic retrieval", "MiniLM-L6-v2 + FAISS"],
             ["Matching engine", "6 weighted components"], ["Skill-gap analysis", "evidence + readiness"],
             ["Customization", "drafts + grounding check"], ["Interview preparation", "questions + feedback"],
             ["Career assistant", "intent routing → services"], ["Application tracker", "statuses · dates · reminders"]]
    for k, lines in enumerate(names):
        s.box(35 + (k % 2) * 290, 370 + (k // 2) * 92, 275, 76, lines)
    s.box(35, 745, 565, 88, ["Shared modules", "skill relationships · education assessment",
                             "grounding validator · llm_provider (null default)"], fill=FILL2)
    s.arrow([(320, 287), (320, 333)])

    s.boundary(640, 335, 245, 515, "EXTERNAL (optional)", color=OPT_LINE)
    s.box(660, 420, 205, 170, ["OpenAI-compatible", "LLM endpoint", "used only when", "LLM_PROVIDER =", "openai_compatible"],
          fill=OPT, stroke=OPT_LINE, dashed=True)
    s.lines(762, 640, ["Only rewrites grounded", "text; output is validated", "and discarded on failure"],
            color=OPT_LINE)
    s.arrow([(600, 789), (630, 789), (630, 505), (658, 505)], dashed=True, color=OPT_LINE)

    s.boundary(15, 885, 870, 290, "DATA TIER (local files)")
    stores = [["SQLite DB", "SQLAlchemy 2", "users, resumes,", "results, tracker"],
              ["Resume files", "generated names", "not web-served"],
              ["Dataset", "320 opportunities", "15 domains (JSON)", "read-only"],
              ["FAISS index", "960 vectors", "384 dimensions", "version 1.2"],
              ["Embedding", "all-MiniLM-L6-v2", "local model cache"]]
    for k, lines in enumerate(stores):
        s.box(30 + k * 170, 925, 160, 230, lines, fill=STORE, stroke=STORE_LINE)
    s.arrow([(320, 850), (320, 923)], label="read / write", label_pos=(390, 893))
    save("fig_4_1_architecture", s)


# ---------------------------------------------------------------------------
# Figure 4.2 — use-case diagram
# ---------------------------------------------------------------------------
def actor(s: Svg, x, y, label, sub=None, color=INK):
    s.add(f'<circle cx="{x}" cy="{y}" r="15" fill="white" stroke="{color}" stroke-width="1.8"/>')
    s.line(x, y + 15, x, y + 58, color=color, width=1.8)
    s.line(x - 25, y + 30, x + 25, y + 30, color=color, width=1.8)
    s.line(x, y + 58, x - 20, y + 90, color=color, width=1.8)
    s.line(x, y + 58, x + 20, y + 90, color=color, width=1.8)
    s.text(x, y + 115, label, size=T, weight="bold", color=color)
    if sub:
        s.text(x, y + 135, sub, size=N, color=MUTED)


def use_case() -> None:
    s = Svg(900, 1030)
    s.boundary(175, 10, 515, 1005, "AI Career Companion", color=NAVY)
    cases = ["Register / sign in / sign out", "Manage career profile", "Upload and process resume",
             "Review structured resume", "Search opportunities", "View ranked job matches",
             "Analyse skill gap for a job", "Generate resume + cover letter", "Edit and export (PDF / DOCX)",
             "Generate interview preparation", "Practise a mock answer", "Converse with the assistant",
             "Track applications and dates", "View dashboard and reminders"]
    cx, rx = 432, 228
    ys = [72 + k * 67 for k in range(len(cases))]
    for y, c in zip(ys, cases):
        s.add(f'<ellipse cx="{cx}" cy="{y}" rx="{rx}" ry="27" fill="{FILL}" stroke="{NAVY}" stroke-width="1.5"/>')
        s.text(cx, y + 5.5, c, size=B)
    actor(s, 85, 40, "Visitor", "not signed in")
    actor(s, 85, 470, "Student", "registered user")
    s.line(112, 85, cx - rx, ys[0], color="#7d8996", width=1.2)
    for y in ys:
        s.line(112, 515, cx - rx, y, color="#7d8996", width=1.2)
    actor(s, 800, 470, "LLM", "optional, external", color=OPT_LINE)
    for k in (7, 9, 11):
        s.line(cx + rx, ys[k], 775, 515, color=OPT_LINE, dashed=True, width=1.3)
    s.lines(800, 640, ["Rewrites grounded", "drafts only; output", "validated, with a", "deterministic", "fallback"],
            color=OPT_LINE)
    s.lines(800, 830, ["Everything except", "sign-up / sign-in", "needs a session", "and acts only on", "the user's own data"])
    save("fig_4_2_use_case", s)


# ---------------------------------------------------------------------------
# Figure 4.3 — level-1 data-flow diagram with trust boundaries
# ---------------------------------------------------------------------------
def process(s: Svg, x, y, w, h, num, title, sub):
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{FILL}" stroke="{NAVY}" stroke-width="1.6"/>')
    s.line(x, y + 28, x + w, y + 28, color=NAVY, width=1.2)
    s.text(x + w / 2, y + 20, num, size=N, weight="bold", color=NAVY)
    s.text(x + w / 2, y + 54, title, size=T, weight="bold")
    s.lines(x + w / 2, y + 77, sub)


def datastore(s: Svg, x, y, w, label, sub=""):
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="48" fill="{STORE}" stroke="none"/>')
    s.add(f'<path d="M {x + w} {y} L {x} {y} L {x} {y + 48} L {x + w} {y + 48}" stroke="{STORE_LINE}" '
          f'stroke-width="1.6" fill="none"/>')
    s.text(x + 9, y + 20, label, size=B, weight="bold", anchor="start")
    if sub:
        s.text(x + 9, y + 39, sub, size=N, anchor="start", color=MUTED)


def dfd() -> None:
    s = Svg(900, 1010)
    s.boundary(8, 10, 142, 990, "TB1 device", color="#7d8996")
    s.box(18, 440, 122, 74, ["Student", "browser"], fill="white")
    s.lines(79, 545, ["requests carry", "the HttpOnly", "session cookie"])
    s.boundary(160, 10, 605, 990, "TB2 backend + local storage", color=NAVY)
    s.boundary(775, 10, 117, 990, "TB3 external", color=OPT_LINE)
    s.box(783, 560, 101, 120, ["LLM", "endpoint", "optional", "(if set)"], fill=OPT, stroke=OPT_LINE, dashed=True,
          size=N)

    pw, ph, px = 205, 120, 180
    rows = [50, 245, 440, 640, 840]
    procs = [("P1", "Authenticate", ["register · login", "logout · lookup"]),
             ("P2", "Process resume", ["validate · extract", "sections · structure"]),
             ("P3", "Retrieve + match", ["embed · FAISS", "weighted scoring"]),
             ("P4", "Gap + materials", ["skill gap · drafts", "interview prep"]),
             ("P5", "Assistant + tracker", ["intent routing", "applications"])]
    for y, (n, t, sub) in zip(rows, procs):
        process(s, px, y, pw, ph, n, t, sub)

    sx, sw = 535, 220
    datastore(s, sx, 86, sw, "D1 users + sessions", "Argon2id · SHA-256")
    datastore(s, sx, 236, sw, "D2 resume files", "generated names")
    datastore(s, sx, 316, sw, "D3 parsed resume data", "sections · JSON · context")
    datastore(s, sx, 476, sw, "D4 dataset + FAISS", "320 jobs · read-only")
    datastore(s, sx, 640, sw, "D5 generated materials", "gaps · drafts · preps")
    datastore(s, sx, 876, sw, "D6 chats + applications", "per-user rows")

    for y in rows:
        s.arrow([(140, 477), (px - 2, y + ph / 2)], both=True)
    s.arrow([(385, 110), (533, 110)], both=True, label="hashes", label_pos=(459, 102))
    s.arrow([(385, 280), (533, 260)], label="file bytes", label_pos=(459, 262))
    s.arrow([(385, 330), (533, 340)], both=True, label="results", label_pos=(459, 328))
    s.arrow([(533, 352), (387, 470)], label="context", label_pos=(470, 418))
    s.arrow([(533, 500), (387, 500)], label="chunk scores", label_pos=(459, 492))
    s.arrow([(533, 515), (387, 665)], label="requirements", label_pos=(468, 596))
    s.arrow([(385, 700), (533, 664)], both=True, label="analyses", label_pos=(459, 676))
    s.arrow([(385, 900), (533, 900)], both=True, label="messages", label_pos=(459, 892))
    s.arrow([(385, 735), (833, 735), (833, 682)], dashed=True, color=OPT_LINE,
            label="grounded evidence", label_pos=(640, 728))
    s.arrow([(860, 682), (860, 800), (282, 800), (282, 762)], dashed=True, color=OPT_LINE,
            label="JSON → validated or discarded", label_pos=(570, 793))
    save("fig_4_3_dfd", s)


# ---------------------------------------------------------------------------
# Figure 4.4 — entity-relationship diagram (placed rotated on its own page)
# ---------------------------------------------------------------------------
def table(s: Svg, x, y, w, name, cols):
    h = 28 + 20 * len(cols) + 8
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="white" stroke="{NAVY}" stroke-width="1.5"/>')
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="4" fill="{NAVY}"/>')
    s.text(x + w / 2, y + 20, name, size=B, weight="bold", color="white", family=MONO)
    for k, c in enumerate(cols):
        s.text(x + 9, y + 48 + k * 20, c, size=N, anchor="start", family=MONO,
               weight="bold" if c.startswith("PK") else "normal")
    return y + h


def erd() -> None:
    s = Svg(1300, 880)
    lab = lambda x, y, t, a="start": s.text(x, y, t, size=N, color=NAVY, weight="bold", anchor=a)
    table(s, 20, 60, 230, "users", ["PK id", "full_name", "email (unique)", "password_hash", "created_at"])
    table(s, 20, 245, 230, "auth_sessions", ["PK id", "FK user_id", "token_hash", "expires_at"])
    table(s, 20, 420, 230, "conversations", ["PK id", "FK user_id", "active_job_id", "FK active_resume_id", "title"])
    table(s, 20, 620, 230, "conversation_messages", ["PK id", "FK conversation_id", "role · intent", "content",
                                                      "metadata_json"])
    table(s, 310, 60, 290, "candidate_profiles", ["PK id", "FK user_id", "education · degree",
                                                   "interests · roles (JSON)", "skills (JSON) · goals"])
    table(s, 310, 250, 290, "resumes", ["PK id", "FK candidate_profile_id", "original_filename",
                                         "stored_filename", "file_type · file_size", "status"])
    table(s, 310, 460, 290, "application_customizations", ["PK id", "FK user_id", "FK resume_id",
                                                            "job_id · version", "data (JSON)",
                                                            "UQ (resume, job, version)"])
    table(s, 310, 670, 290, "interview_preparations", ["PK id", "FK user_id", "FK resume_id", "job_id · version",
                                                        "data (JSON)", "UQ (resume, job, version)"])
    table(s, 680, 60, 270, "resume_extractions", ["PK id", "FK resume_id (unique)", "raw_text", "normalized_text"])
    table(s, 680, 215, 270, "resume_sections", ["PK id", "FK resume_id", "name · content", "position"])
    table(s, 680, 370, 270, "structured_resumes", ["PK id", "FK resume_id (unique)", "data (JSON)"])
    table(s, 680, 505, 270, "candidate_contexts", ["PK id", "FK candidate_profile_id", "FK resume_id",
                                                    "context_json"])
    table(s, 680, 660, 270, "applications", ["PK id · FK user_id", "source (dataset|manual)", "job_id (nullable)",
                                              "status · dates · notes", "FK customization_id", "FK interview_prep_id",
                                              "UQ (user_id, job_id)"])
    table(s, 1010, 60, 250, "skill_gaps", ["PK id", "FK user_id", "job_id", "data (JSON)", "UQ (user_id, job_id)"])
    s.box(1010, 250, 250, 120, ["Opportunity dataset", "JSON file, not in DB", "320 records,", "keyed by job_id"],
          fill=STORE, stroke=STORE_LINE, dashed=True, size=N)
    s.box(1010, 430, 250, 140, ["Legacy tables", "no active feature:", "selected_jobs", "learning_roadmaps",
                                "roadmap_items", "progress_events"], fill=GREY_FILL, stroke=GREY_LINE, size=N)

    s.arrow([(135, 196), (135, 243)]); lab(143, 214, "1"); lab(143, 238, "0..*")
    s.arrow([(250, 90), (308, 90)]); lab(256, 82, "1"); lab(302, 82, "0..1", "end")
    s.arrow([(135, 576), (135, 618)]); lab(143, 594, "1"); lab(143, 612, "0..*")
    s.arrow([(455, 196), (455, 248)]); lab(463, 214, "1"); lab(463, 242, "0..*")
    s.line(600, 300, 640, 300); s.line(640, 90, 640, 535); lab(606, 293, "1")
    for y, card in ((90, "0..1"), (245, "0..*"), (400, "0..1"), (535, "0..*")):
        s.arrow([(640, y), (678, y)]); lab(674, y - 7, card, "end")
    s.arrow([(455, 414), (455, 458)]); lab(463, 432, "1"); lab(463, 452, "0..*")
    s.arrow([(310, 380), (285, 380), (285, 720), (308, 720)]); lab(304, 373, "1", "end"); lab(304, 713, "0..*", "end")
    s.arrow([(678, 720), (602, 720)]); lab(610, 712, "0..1"); lab(672, 712, "0..*", "end")
    s.arrow([(678, 700), (640, 700), (640, 560), (602, 560)]); lab(610, 552, "0..1")
    s.arrow([(1135, 196), (1135, 248)], dashed=True, label="job_id", label_pos=(1135, 228))
    s.arrow([(950, 800), (1285, 800), (1285, 310), (1262, 310)], dashed=True, label="job_id", label_pos=(1120, 793))
    s.text(20, 32, "Every per-user table carries FK user_id → users.id; only auth_sessions and candidate_profiles "
                   "are drawn, for readability.", size=N, anchor="start", color=MUTED)
    s.text(20, 868, "PK primary key · FK foreign key · UQ unique · dashed = logical reference by job_id. "
                    "Source: backend/app/models (key columns only).", size=N, anchor="start", color=MUTED)
    save("fig_4_4_erd", s)


# ---------------------------------------------------------------------------
# Sequence-diagram helper
# ---------------------------------------------------------------------------
def sequence(name, participants, steps, height, width=900, margin=95):
    s = Svg(width, height)
    n = len(participants)
    gap = (width - 2 * margin) / (n - 1)
    xs = [margin + k * gap for k in range(n)]
    for x, (title, sub) in zip(xs, participants):
        s.box(x - 88, 12, 176, 60, [title, sub], size=N)
        s.line(x, 72, x, height - 12, color="#aab4be", dashed=True, width=1.2)
    y = 108
    frames = []
    for step in steps:
        kind = step[0]
        if kind == "msg":
            _, a, b, label, *rest = step
            ret = bool(rest and rest[0])
            x1, x2 = xs[a], xs[b]
            if a == b:
                s.arrow([(x1, y - 8), (x1 + 40, y - 8), (x1 + 40, y + 10), (x1 + 4, y + 10)])
                s.text(x1 + 48, y + 6, label, size=N, anchor="start")
                y += 40
                continue
            s.arrow([(x1, y), (x2 + (-4 if x2 > x1 else 4), y)], dashed=ret)
            s.text((x1 + x2) / 2, y - 7, label, size=N, color=MUTED if ret else INK)
            y += 38
        elif kind == "note":
            _, label = step
            s.add(f'<rect x="{xs[0] - 80}" y="{y - 18}" width="{xs[-1] - xs[0] + 160}" height="28" fill="{WARN_FILL}" '
                  f'stroke="#d6b25e" rx="3"/>')
            s.text((xs[0] + xs[-1]) / 2, y + 1, label, size=N, italic=True)
            y += 42
        elif kind == "begin":
            frames.append((step[1], y - 26))
            y += 20
        elif kind == "end":
            label, y0 = frames.pop()
            s.add(f'<rect x="14" y="{y0}" width="{width - 28}" height="{y - y0 - 16}" fill="none" stroke="{GREY_LINE}" '
                  f'stroke-dasharray="5 3"/>')
            s.add(f'<rect x="14" y="{y0}" width="{len(label) * 7.6 + 18}" height="22" fill="{GREY_FILL}" stroke="{GREY_LINE}"/>')
            s.text(23, y0 + 16, label, size=N, anchor="start", weight="bold", color=MUTED)
            y += 10
    save(name, s)


def resume_sequence() -> None:
    P = [("Student", "browser"), ("React SPA", "resumeService.ts"), ("FastAPI", "routers + services"),
         ("Storage", "SQLite + files")]
    steps = [
        ("msg", 0, 1, "choose file, “Process resume”"),
        ("note", "every request: session cookie → require_current_user + ownership check"),
        ("begin", "pipeline run by the SPA in order (stops at the first failure)"),
        ("msg", 1, 2, "POST /profiles/{id}/resumes"),
        ("msg", 2, 2, "check type, signature, ≤ 10 MiB"),
        ("msg", 2, 3, "file + resumes row"),
        ("msg", 2, 1, "201 resume (no file path)", True),
        ("msg", 1, 2, "POST /resumes/{id}/extract-text"),
        ("msg", 2, 2, "pypdf / python-docx, normalise"),
        ("msg", 2, 3, "resume_extractions"),
        ("msg", 1, 2, "POST /resumes/{id}/detect-sections"),
        ("msg", 2, 3, "resume_sections"),
        ("msg", 1, 2, "POST /resumes/{id}/structure"),
        ("msg", 2, 3, "structured_resumes"),
        ("msg", 1, 2, "POST …/candidate-context"),
        ("msg", 2, 3, "candidate_contexts"),
        ("msg", 2, 1, "200 candidate context", True),
        ("end",),
        ("msg", 1, 0, "Resume Results page", True),
        ("msg", 1, 2, "GET /resumes/{id}/job-matches"),
        ("msg", 2, 2, "FAISS retrieval → 6-part score"),
        ("msg", 2, 1, "ranked matches + reasoning", True),
    ]
    sequence("fig_4_5_resume_sequence", P, steps, 930)


def auth_sequence() -> None:
    P = [("Browser", "React SPA"), ("FastAPI", "auth router + service"), ("SQLite", "users · auth_sessions")]
    steps = [
        ("msg", 0, 1, "POST /api/auth/register"),
        ("msg", 1, 1, "e-mail valid? password 8–128?"),
        ("msg", 1, 2, "user (Argon2id hash) + profile"),
        ("msg", 1, 1, "create session (as for login)"),
        ("msg", 1, 0, "201 + session cookie; 409 duplicate", True),
        ("msg", 0, 1, "POST /api/auth/login"),
        ("msg", 1, 2, "find user by e-mail; verify hash"),
        ("msg", 1, 1, "token = token_urlsafe(48)"),
        ("msg", 1, 2, "store SHA-256(token), 14-day expiry"),
        ("msg", 1, 0, "Set-Cookie: HttpOnly; SameSite=Lax", True),
        ("note", "cookie is Secure whenever APP_ENV is not “development”"),
        ("msg", 0, 1, "GET /api/… (cookie sent automatically)"),
        ("msg", 1, 2, "look up SHA-256(cookie); check expiry"),
        ("msg", 1, 0, "200 own data · 401 · 404 if not owner", True),
        ("msg", 0, 0, "on 401: back to sign-in"),
        ("msg", 0, 1, "POST /api/auth/logout"),
        ("msg", 1, 2, "delete session row"),
        ("msg", 1, 0, "204, cookie cleared", True),
    ]
    sequence("fig_4_7_auth_sequence", P, steps, 780, margin=110)


# ---------------------------------------------------------------------------
# Flowcharts
# ---------------------------------------------------------------------------
def decision(s: Svg, cx, cy, w, h, lines):
    s.add(f'<polygon points="{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}" '
          f'fill="{WARN_FILL}" stroke="{WARN_LINE}" stroke-width="1.6"/>')
    for k, l in enumerate(lines):
        s.text(cx, cy + 5 - (len(lines) - 1) * 9.5 + k * 19, l, size=B)


def llm_path() -> None:
    s = Svg(900, 1010)
    s.box(260, 15, 380, 70, ["Deterministic result", "already grounded in evidence"], fill=FILL2)
    decision(s, 450, 150, 300, 90, ["LLM_PROVIDER", "setting?"])
    s.arrow([(450, 85), (450, 103)])
    s.box(15, 230, 225, 100, ["Grounded Fallback", "deterministic result", "shown to the user"])
    s.arrow([(300, 150), (127, 150), (127, 228)], label="none (default)", label_pos=(214, 142))
    s.box(260, 250, 380, 90, ["Build grounded input", "evidence IDs · allowed claims", "strict JSON contract"],
          fill=OPT, stroke=OPT_LINE)
    s.arrow([(450, 195), (450, 248)], color=OPT_LINE, label="openai_compatible", label_pos=(530, 228))
    s.box(260, 375, 380, 80, ["Call /chat/completions", "JSON mode · timeout (default 20 s)"], fill=OPT,
          stroke=OPT_LINE)
    s.arrow([(450, 340), (450, 373)], color=OPT_LINE)
    decision(s, 450, 545, 360, 110, ["Schema, evidence-ID,", "keyword and fabrication", "checks pass?"])
    s.arrow([(450, 455), (450, 488)])
    s.box(665, 505, 195, 80, ["LLM-assisted", "mode = llm"])
    s.arrow([(630, 545), (663, 545)], label="yes", label_pos=(646, 537))
    decision(s, 450, 700, 270, 90, ["Repair already", "attempted?"])
    s.arrow([(450, 600), (450, 653)], label="no", label_pos=(472, 630))
    s.box(15, 660, 225, 80, ["One repair call", "violations sent back"], fill=OPT, stroke=OPT_LINE)
    s.arrow([(315, 700), (242, 700)], label="no", label_pos=(278, 692))
    s.arrow([(127, 660), (127, 415), (258, 415)], color=OPT_LINE)
    s.box(260, 795, 380, 110, ["Deterministic fallback", "fallback_reason recorded", "(timeout, HTTP error, bad JSON,",
                               "failed validation)"])
    s.arrow([(450, 745), (450, 793)], label="yes", label_pos=(472, 772))
    s.arrow([(640, 400), (885, 400), (885, 850), (642, 850)], dashed=True, color=OPT_LINE)
    s.text(760, 390, "error / timeout", size=N, color=OPT_LINE)
    s.lines(450, 950, ["The LLM never selects jobs, computes scores, decides gaps,",
                       "manages the tracker or authenticates users."])
    save("fig_4_6_llm_path", s)


def retrieval_flow() -> None:
    s = Svg(900, 1000)
    left = [(["Candidate context", "profile + structured resume"], FILL2),
            (["Normalise terms", "skills, roles, interests,", "education, projects"], FILL),
            (["Build query", "explicit query, or the", "first 40 normalised terms"], FILL),
            (["Embed query", "MiniLM-L6-v2 → 384-d,", "L2-normalised"], FILL),
            (["Exact FAISS search", "IndexFlatIP, all 960 chunks", "(cosine similarity)"], FILL),
            (["Aggregate per job", "best chunk + 0.05 × Σ others"], FILL),
            (["Top-k opportunities", "10 for matching, 5 for search"], FILL)]
    y = 15
    for k, (lines, fill) in enumerate(left):
        h = 72 if len(lines) == 2 else 90
        s.box(15, y, 400, h, lines, fill=fill)
        if k:
            s.arrow([(215, y - 26), (215, y - 2)])
        y += h + 28
    flag_y = y
    s.box(15, flag_y, 400, 110, ["Query-confidence flag", "share of query words found in", "the catalogue: ≥ 0.5 →",
                                 "confident, else unsupported_area"], fill=WARN_FILL, stroke=WARN_LINE)
    s.arrow([(215, flag_y - 26), (215, flag_y - 2)])
    s.box(475, 15, 410, 72, ["For each retrieved job", "load its structured record"], fill=FILL2)
    top_k_mid = flag_y - 28 - 36
    s.arrow([(415, top_k_mid), (445, top_k_mid), (445, 51), (473, 51)])
    comps = [("Required", "0.35", "exact / alias"), ("Preferred", "0.15", "related = 0.5"),
             ("Experience", "0.15", "rule-based"), ("Projects", "0.15", "term overlap"),
             ("Education", "0.10", "met / partial / not"), ("Qualifications", "0.10", "certifications")]
    for k, (name, wt, sub) in enumerate(comps):
        s.box(475 + (k % 2) * 210, 120 + (k // 2) * 92, 200, 80, [f"{name} {wt}", sub])
    s.arrow([(680, 87), (680, 118)])
    s.box(475, 420, 410, 110, ["Match score (0–100)", "Σ wᵢ·sᵢ / Σ wᵢ × 100 over the", "components that apply;",
                               "no evidence → excluded, not 0"])
    s.arrow([(680, 396), (680, 418)])
    s.box(475, 560, 410, 90, ["Explanation", "matched / missing skills,", "self-reported skills, reasoning"])
    s.arrow([(680, 530), (680, 558)])
    s.box(475, 680, 410, 72, ["Sort and return", "match ↓, retrieval ↓, job_id ↑"], fill=FILL2)
    s.arrow([(680, 650), (680, 678)])
    s.lines(450, 965, ["Retrieval chooses which records are considered; deterministic code orders and explains them."])
    save("fig_5_1_retrieval_matching", s)


def grounding_flow() -> None:
    s = Svg(900, 1000)
    s.box(15, 15, 420, 100, ["Evidence records", "skills, reliable projects, education,", "profile (self-reported), with IDs"],
          fill=FILL2)
    s.box(465, 15, 420, 100, ["Job record", "required / preferred skills,", "title, company, requirements"], fill=FILL2)
    s.box(15, 155, 420, 110, ["Keyword alignment", "supported (direct evidence)", "partial (related evidence)",
                              "unsupported (absent)"])
    s.box(465, 155, 420, 110, ["Deterministic drafts", "summary · skill and project order", "cover letter · questions"])
    s.arrow([(225, 115), (225, 153)])
    s.arrow([(675, 115), (675, 153)])
    s.arrow([(435, 210), (463, 210)])
    s.boundary(15, 300, 870, 345, "Grounding validator — every generated sentence")
    checks = [["Unsupported keyword", "job term absent from the", "evidence (title and", "company name allowed)"],
              ["Fabrication patterns", "invented metrics (%, ×),", "“led a team”,", "“N years of experience”"],
              ["Unsupported claims", "technologies, degrees,", "employers, awards,", "quoted project names"],
              ["Parser reliability", "fragment projects excluded;", "parser warnings block", "a “passed” status"]]
    for k, c in enumerate(checks):
        s.box(35 + (k % 2) * 425, 335 + (k // 2) * 150, 405, 135, c)
    s.arrow([(675, 265), (675, 285), (450, 285), (450, 298)])
    decision(s, 450, 725, 320, 100, ["Sentence fails", "a check?"])
    s.arrow([(450, 645), (450, 673)])
    s.box(15, 830, 360, 90, ["Remove sentence", "recorded in removed_claims"], fill="#fbeaea", stroke="#a04040")
    s.arrow([(290, 725), (195, 725), (195, 828)], label="yes", label_pos=(242, 717))
    s.box(525, 830, 360, 90, ["Keep sentence", "passed = nothing removed", "and no parser warning"])
    s.arrow([(610, 725), (705, 725), (705, 828)], label="no", label_pos=(658, 717))
    s.lines(450, 955, ["Edits are re-validated on save; generation is refused (HTTP 409)",
                       "when only unreliable project fragments remain."])
    save("fig_5_2_grounding", s)


def view_map() -> None:
    s = Svg(900, 800)
    s.box(15, 15, 250, 72, ["Sign in / Sign up", "/login · /signup"], fill=FILL2)
    s.box(330, 15, 250, 72, ["Dashboard", "/dashboard"])
    s.arrow([(265, 51), (328, 51)], label="session", label_pos=(296, 43))
    s.boundary(15, 115, 870, 325, "Sidebar navigation (every signed-in page)", color=NAVY)
    s.arrow([(455, 87), (455, 113)])
    nav = [("Career Profile", "/profile"), ("Resume Analyzer", "/resume"), ("Recommendations", "/careers"),
           ("Application Tracker", "/applications"), ("Skill Gap Analysis", "/skills"), ("AI Career Assistant", "/assistant"),
           ("Progress Tracker", "/progress"), ("Settings", "/settings"), ("Learning Roadmap", "not implemented")]
    for k, (t, p) in enumerate(nav):
        legacy = p == "not implemented"
        s.box(35 + (k % 3) * 280, 150 + (k // 3) * 93, 265, 75, [t, p], fill=GREY_FILL if legacy else FILL,
              stroke=GREY_LINE if legacy else NAVY, dashed=legacy)
    s.boundary(15, 465, 870, 305, "Detail pages (opened from the page named below each)", color=GREY_LINE)
    details = [("Resume Results", "/resume/results", "from Resume Analyzer"),
               ("Job Details", "/jobs/{id}", "from Recommendations"),
               ("Application Details", "/applications/{id}", "from Application Tracker"),
               ("Customize Application", "/customize?job={id}", "from Job Details / Skill Gap"),
               ("Interview Preparation", "/interview-prep?job={id}", "from Job Details / Customize")]
    for k, (t, p, origin) in enumerate(details):
        col, row = (k % 3, k // 3)
        x, y = 35 + col * 280, 500 + row * 135
        s.box(x, y, 265, 75, [t, p])
        s.text(x + 132, y + 98, origin, size=N, color=MUTED, italic=True)
    s.lines(450, 790, ["Job-scoped pages keep ?job= in the URL, so a refresh restores the opportunity."])
    save("fig_6_1_view_map", s)


def retrieval_chart() -> None:
    """Grouped bars: M4.2 baseline vs M4.3 final (values from the tracked evaluation reports)."""
    metrics = [("Hit@1", 0.885, 1.000), ("Precision@5", 0.654, 0.662), ("Recall@5", 0.874, 0.883),
               ("nDCG@5", 0.961, 0.969), ("MRR@10", 0.942, 1.000)]
    base_c, final_c = "#eb6834", "#2a78d6"
    s = Svg(900, 500)
    left, top, plot_w, plot_h = 60, 70, 820, 330
    for k in range(6):
        v = k / 5
        y = top + plot_h - v * plot_h
        s.line(left, y, left + plot_w, y, color="#e3e6ea" if k else "#8c96a1", width=1.2)
        s.text(left - 10, y + 5, f"{v:.1f}", size=B, anchor="end", color=MUTED)
    group_w = plot_w / len(metrics)
    bw = 54
    for k, (name, b, f) in enumerate(metrics):
        gx = left + k * group_w + group_w / 2
        for j, (val, col) in enumerate(((b, base_c), (f, final_c))):
            x = gx - bw - 1 + j * (bw + 2)
            h = val * plot_h
            y = top + plot_h - h
            s.add(f'<path d="M {x} {top + plot_h} L {x} {y + 4} Q {x} {y} {x + 4} {y} L {x + bw - 4} {y} '
                  f'Q {x + bw} {y} {x + bw} {y + 4} L {x + bw} {top + plot_h} Z" fill="{col}"/>')
            s.text(x + bw / 2, y - 7, f"{val:.3f}", size=N, color=INK)
        s.text(gx, top + plot_h + 26, name, size=B, color=INK)
    s.add(f'<rect x="{left}" y="20" width="16" height="16" rx="3" fill="{base_c}"/>')
    s.text(left + 24, 34, "M4.2 frozen baseline", size=B, anchor="start")
    s.add(f'<rect x="{left + 240}" y="20" width="16" height="16" rx="3" fill="{final_c}"/>')
    s.text(left + 264, 34, "M4.3 final (index v1.2)", size=B, anchor="start")
    s.text(left, 480, "26 labelled queries, rule-derived labels. Source: M4_2_BASELINE_REPORT.md, "
                      "M4_3_OPTIMIZED_EVALUATION.md.", size=N, anchor="start", color=MUTED)
    save("fig_7_1_retrieval_metrics", s)


if __name__ == "__main__":
    architecture()
    use_case()
    dfd()
    erd()
    resume_sequence()
    llm_path()
    auth_sequence()
    retrieval_flow()
    grounding_flow()
    view_map()
    retrieval_chart()

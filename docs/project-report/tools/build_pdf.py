"""Renders AI_Career_Companion_Project_Report.pdf from the Markdown source.

    .venv\\Scripts\\python.exe docs\\project-report\\tools\\build_pdf.py

The Markdown is converted to print HTML (same parser helpers as build_report.py), printed
with headless Chrome (A4, document outline from the headings), and then:
  1. the page of every heading and caption is read from the PDF outline;
  2. the table of contents, list of figures and list of tables are filled with those
     page numbers and the HTML is printed again (repeated until the numbers are stable);
  3. page numbers (none on the title page, roman numerals for the preliminary pages,
     arabic from Chapter 1) and the running header are stamped on with reportlab.
Internal links (table of contents, lists) and the bookmark outline are preserved.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_report import HEADER_TEXT, latex_runs, parse_table, rotated_copy, split_attrs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AI_Career_Companion_Project_Report.md"
OUTPUT = ROOT / "AI_Career_Companion_Project_Report.pdf"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

CSS = """
@page { size: A4; margin: 1in 1in 1in 1.5in; }
html { font-family: 'Times New Roman', Times, serif; font-size: 12pt; color: #111; }
body { margin: 0; line-height: 1.5; }
p { margin: 0 0 6pt; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }
.center { text-align: center; margin-bottom: 4pt; }
h1, h2, h3, .prelim { color: #1f3a5f; line-height: 1.2; break-after: avoid; }
h1 { font-size: 16pt; margin: 0 0 18pt; break-before: page; }
h2 { font-size: 13.5pt; margin: 14pt 0 6pt; }
h3 { font-size: 12pt; font-style: italic; margin: 10pt 0 4pt; }
.prelim { font-size: 15pt; text-align: center; margin: 0 0 18pt; break-before: page; font-weight: bold; }
.titlepage { break-after: page; padding-top: 0.6in; text-align: center; }
.titlepage .title { font-size: 20pt; font-weight: bold; color: #1f3a5f; margin: 0 0 30pt; line-height: 1.3; }
.titlepage p { text-align: center; margin: 0 0 6pt; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 10pt; }
code, .ref { overflow-wrap: anywhere; }
table.data .nw { white-space: nowrap; }
pre { font-family: Consolas, 'Courier New', monospace; font-size: 9pt; line-height: 1.35;
      background: #f3f5f8; border: 1px solid #c8ced6; padding: 6pt 8pt; margin: 4pt 0 10pt;
      white-space: pre-wrap; break-inside: avoid; }
ul, ol { margin: 0 0 6pt; padding-left: 22pt; }
li { margin: 0 0 3pt; text-align: left; }
table.data { border-collapse: collapse; width: 100%; margin: 0 0 12pt; font-size: 10pt; line-height: 1.25; }
table.data th, table.data td { border: 1px solid #9aa3ad; padding: 3pt 5pt; vertical-align: top; text-align: left; }
table.data th { background: #dce6f1; }
table.data td.num { text-align: right; white-space: nowrap; }
table.data tr { break-inside: avoid; }
h5.tabcap { font-size: 11pt; font-weight: bold; text-align: center; margin: 10pt 0 4pt; color: #111; break-after: avoid; }
figure { margin: 8pt 0 12pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 8.2in; }
figure.rotated { break-before: page; break-after: page; }
figure.rotated img { height: 8.4in; width: auto; max-height: none; max-width: 100%; }
h6.figcap { font-size: 11pt; font-weight: normal; font-style: italic; text-align: center; margin: 4pt 0 0; color: #111; }
.note { font-size: 11pt; font-style: italic; background: #fff8e5; border: 1px solid #d6b25e; padding: 5pt 8pt; margin: 0 0 12pt; text-align: left; }
.eq { text-align: center; margin: 4pt 0 8pt; }
.ref { padding-left: 1cm; text-indent: -1cm; font-size: 11pt; line-height: 1.3; text-align: left; margin-bottom: 6pt; }
.sigs { display: flex; justify-content: space-around; margin: 40pt 0 16pt; text-align: center; font-size: 11pt; line-height: 1.3; }
.sigs div { min-width: 40%; }
.toc { list-style: none; padding: 0; margin: 0; }
.toc li { display: flex; align-items: baseline; margin: 0 0 2pt; line-height: 1.22; text-align: left; }
.toc li a { color: #111; text-decoration: none; }
.toc li .dots { flex: 1; border-bottom: 1px dotted #777; margin: 0 4pt; transform: translateY(-3pt); }
.toc li .pg { min-width: 22pt; text-align: right; }
.toc .l1 { font-weight: bold; margin-top: 5pt; }
.toc .l2 { padding-left: 16pt; }
.toc .l3 { padding-left: 34pt; font-size: 11pt; }
a { color: inherit; }
"""

INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\$[^$]+\$|\*[^*\s][^*]*?\*)")


def math_html(src: str) -> str:
    parts = []
    for text, fmt in latex_runs(src):
        t = html.escape(text)
        if fmt.get("bold"):
            t = f"<b>{t}</b>"
        elif not fmt.get("upright") and any(c.isalpha() for c in text) and len(text) < 4:
            t = f"<i>{t}</i>"
        if fmt.get("subscript"):
            t = f"<sub>{t}</sub>"
        if fmt.get("superscript"):
            t = f"<sup>{t}</sup>"
        parts.append(t)
    return "".join(parts)


def inline(text: str) -> str:
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<strong>{inline(part[2:-2])}</strong>")
        elif part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        elif part.startswith("$") and part.endswith("$") and len(part) > 2:
            out.append(math_html(part[1:-1]))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<em>{inline(part[1:-1])}</em>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(inline(text)))


class Entry:
    def __init__(self, kind: str, level: int, title: str, anchor: str) -> None:
        self.kind, self.level, self.title, self.anchor = kind, level, title, anchor


def to_html(page_of: dict[str, str]) -> tuple[str, list[Entry]]:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    entries: list[Entry] = []
    chapter = section_no = sub_no = 0
    in_title = in_refs = False
    pending_caption: str | None = None
    buf: list[str] = []
    list_kind: str | None = None
    counter = 0

    def anchor() -> str:
        nonlocal counter
        counter += 1
        return f"a{counter}"

    def close_list():
        nonlocal list_kind
        if list_kind:
            body.append(f"</{list_kind}>")
            list_kind = None

    def flush():
        nonlocal buf
        if not buf:
            return
        text, attrs = split_attrs(" ".join(s.strip() for s in buf))
        buf = []
        if in_refs and re.match(r"\[\d+\]", text):
            body.append(f'<p class="ref">{inline(text)}</p>')
        else:
            cls = ' class="center"' if "center" in attrs else ""
            body.append(f"<p{cls}>{inline(text)}</p>")

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        m = re.fullmatch(r"<!--\s*(.+?)\s*-->", s)
        if m:
            flush(); close_list()
            d = m.group(1)
            if d == "titlepage":
                in_title = True
                body.append('<section class="titlepage">')
            elif d == "frontmatter":
                in_title = False
                body.append("</section>")
            elif d in ("toc", "lof", "lot"):
                body.append(f"<!--LIST:{d}-->")
            elif d.startswith("signatures:"):
                cells = [c.strip() for c in d.split(":", 1)[1].split("|")]
                pairs = [(cells[k], cells[k + 1] if k + 1 < len(cells) else "") for k in range(0, len(cells), 2)]
                body.append('<div class="sigs">' + "".join(
                    f"<div>______________________________<br><strong>{inline(n)}</strong><br>{inline(r)}</div>"
                    for n, r in pairs) + "</div>")
            elif d == "references":
                in_refs = True
            i += 1
            continue
        if not s:
            flush(); close_list()
            i += 1
            continue
        hm = re.match(r"(#{1,3})\s+(.*)", line)
        if hm:
            flush(); close_list()
            level = len(hm.group(1))
            text, attrs = split_attrs(hm.group(2))
            a = anchor()
            if "title" in attrs:
                body.append(f'<p class="title" id="{a}">{inline(text)}</p>')
            elif "prelim" in attrs:
                body.append(f'<h1 class="prelim" id="{a}">{inline(text)}</h1>')
                if text.upper() != "TABLE OF CONTENTS":
                    entries.append(Entry("toc", 1, text, a))
            elif level == 1:
                in_refs = False
                if "unnumbered" in attrs or "appendix" in attrs:
                    label = text
                else:
                    chapter += 1
                    section_no = sub_no = 0
                    label = f"Chapter {chapter}: {text}"
                body.append(f'<h1 id="{a}">{inline(label)}</h1>')
                entries.append(Entry("toc", 1, label, a))
            elif level == 2:
                section_no += 1
                sub_no = 0
                label = f"{chapter}.{section_no} {text}"
                body.append(f'<h2 id="{a}">{inline(label)}</h2>')
                entries.append(Entry("toc", 2, label, a))
            else:
                sub_no += 1
                label = f"{chapter}.{section_no}.{sub_no} {text}"
                body.append(f'<h3 id="{a}">{inline(label)}</h3>')
                entries.append(Entry("toc", 3, label, a))
            i += 1
            continue
        fm = re.fullmatch(r"!\[(.+?)\]\((.+?)\)(\{\.rotate\})?", s)
        if fm:
            flush(); close_list()
            a = anchor()
            src = (rotated_copy(ROOT / fm.group(2)) if fm.group(3) else ROOT / fm.group(2)).as_uri()
            cls = ' class="rotated"' if fm.group(3) else ""
            body.append(f'<figure{cls}><img src="{src}" alt="{html.escape(plain(fm.group(1)))}">'
                        f'<h6 class="figcap" id="{a}">{inline(fm.group(1))}</h6></figure>')
            entries.append(Entry("lof", 1, fm.group(1), a))
            i += 1
            continue
        if re.match(r"Table [A-Z0-9]+\.\d+:", s):
            flush(); close_list()
            pending_caption = s
            i += 1
            continue
        if s.startswith("|"):
            flush(); close_list()
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i]); i += 1
            rows = parse_table(block)
            if pending_caption:
                a = anchor()
                body.append(f'<h5 class="tabcap" id="{a}">{inline(pending_caption)}</h5>')
                entries.append(Entry("lot", 1, pending_caption, a))
                pending_caption = None
            t = ['<table class="data"><thead><tr>'] + [f'<th{" class=\"nw\"" if " " not in plain(c) and len(plain(c)) <= 16 else ""}>{inline(c)}</th>' for c in rows[0]] + ["</tr></thead><tbody>"]
            numeric_cols = [all(re.fullmatch(r"[\d.,/ %×→–\-msx@()]+", r[k].strip()) for r in rows[1:] if k < len(r))
                            for k in range(len(rows[0]))]
            for r in rows[1:]:
                t.append("<tr>")
                for ci, c in enumerate(r):
                    num = numeric_cols[ci] if ci < len(numeric_cols) else False
                    word = plain(c).strip()
                    cls = "num" if num else ("nw" if " " not in word and len(word) <= 16 else "")
                    t.append(f'<td{f" class=\"{cls}\"" if cls else ""}>{inline(c)}</td>')
                t.append("</tr>")
            t.append("</tbody></table>")
            body.append("".join(t))
            continue
        if s.startswith("```"):
            flush(); close_list()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i]); i += 1
            i += 1
            body.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            flush(); close_list()
            body.append(f'<p class="eq">{math_html(s[2:-2].strip())}</p>')
            i += 1
            continue
        if s.startswith(">"):
            flush(); close_list()
            body.append(f'<p class="note">{inline(s.lstrip("> ").strip())}</p>')
            i += 1
            continue
        bm = re.match(r"-\s+(.*)", s)
        nm = re.match(r"(\d+)\.\s+(.*)", s)
        if bm or nm:
            flush()
            kind = "ul" if bm else "ol"
            if list_kind != kind:
                close_list()
                start = f' start="{nm.group(1)}"' if nm and nm.group(1) != "1" else ""
                body.append(f"<{kind}{start}>")
                list_kind = kind
            item = (bm or nm).group(1 if bm else 2)
            i += 1
            while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() and not re.match(r"\s*(-|\d+\.)\s", lines[i]):
                item += " " + lines[i].strip(); i += 1
            body.append(f"<li>{inline(item)}</li>")
            continue
        buf.append(line)
        i += 1
    flush(); close_list()

    doc = "\n".join(body)
    for kind in ("toc", "lof", "lot"):
        items = []
        for e in entries:
            if e.kind != kind:
                continue
            pg = page_of.get(e.anchor, "000")
            items.append(f'<li class="l{e.level}"><a href="#{e.anchor}">{inline(e.title)}</a>'
                         f'<span class="dots"></span><span class="pg">{pg}</span></li>')
        doc = doc.replace(f"<!--LIST:{kind}-->", '<ul class="toc">' + "".join(items) + "</ul>")
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>AI Career Companion — Project Report</title>"
            f"<style>{CSS}</style></head><body>{doc}</body></html>")
    return page, entries


def print_pdf(html_path: Path, pdf_path: Path) -> None:
    profile = Path(tempfile.gettempdir()) / "ai-career-report-chrome"
    subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                    "--no-pdf-header-footer", "--generate-pdf-document-outline",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)


def outline_pages(pdf_path: Path) -> list[tuple[str, int]]:
    reader = PdfReader(str(pdf_path))
    found: list[tuple[str, int]] = []

    def walk(items):
        for it in items:
            if isinstance(it, list):
                walk(it)
            else:
                found.append((str(it.title).strip(), reader.get_destination_page_number(it)))
    walk(reader.outline)
    return found


def norm(t: str) -> str:
    # Chrome can drop the space at a line wrap inside a long heading, so compare without whitespace.
    return re.sub(r"\s+", "", t)


def roman(n: int) -> str:
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, r in vals:
        while n >= v:
            out += r; n -= v
    return out


def build() -> None:
    work = Path(tempfile.mkdtemp(prefix="report-pdf-"))
    html_path, raw_pdf = work / "report.html", work / "raw.pdf"
    page_of: dict[str, str] = {}
    previous = None
    for attempt in range(4):
        page, entries = to_html(page_of)
        html_path.write_text(page, encoding="utf-8")
        print_pdf(html_path, raw_pdf)
        outline = outline_pages(raw_pdf)
        # Match entries to outline items in document order.
        idx_of: dict[str, int] = {}
        pos = 0
        ordered = [e for e in entries]  # document order already
        titles = [(norm(t), p) for t, p in outline]
        for e in ordered:
            want = norm(plain(e.title))
            for k in range(pos, len(titles)):
                got = titles[k][0]
                if got == want or (len(got) >= 40 and want.startswith(got.rstrip(".… "))):
                    idx_of[e.anchor] = titles[k][1]
                    pos = k + 1
                    break
        missing = [e.title for e in entries if e.anchor not in idx_of]
        if missing:
            raise SystemExit(f"outline is missing {len(missing)} entries, e.g. {missing[:3]}")
        first_front = min(idx_of[e.anchor] for e in entries if e.kind == "toc" and e.level == 1)
        first_main = next(idx_of[e.anchor] for e in entries if e.kind == "toc" and e.title.startswith("Chapter 1:"))

        def label(p: int) -> str:
            return str(p - first_main + 1) if p >= first_main else roman(p - first_front + 1)
        new = {a: label(p) for a, p in idx_of.items()}
        if new == previous:
            break
        previous, page_of = new, new
    else:
        raise SystemExit("page numbers did not stabilise")

    reader = PdfReader(str(raw_pdf))
    writer = PdfWriter(clone_from=reader)
    width, height = A4
    for n, pg in enumerate(writer.pages):
        if n < first_front:
            continue
        overlay_path = work / f"ov{n}.pdf"
        c = canvas.Canvas(str(overlay_path), pagesize=A4)
        c.setFont("Times-Roman", 10)
        c.drawCentredString((width + 0.5 * 72) / 2, 0.55 * 72, label(n))
        if n >= first_main:
            c.setFont("Times-Italic", 9)
            c.setFillColorRGB(0.33, 0.37, 0.42)
            c.drawRightString(width - 1.0 * 72, height - 0.62 * 72, HEADER_TEXT)
            c.setStrokeColorRGB(0.54, 0.58, 0.63)
            c.setLineWidth(0.5)
            c.line(1.5 * 72, height - 0.68 * 72, width - 1.0 * 72, height - 0.68 * 72)
        c.save()
        pg.merge_page(PdfReader(str(overlay_path)).pages[0])
    writer.add_metadata({"/Title": "AI Career Companion: An Intelligent Career Recommendation and Skill-Gap Analysis Platform",
                         "/Author": "Jeswin Jarald", "/Subject": "Academic project report — Infosys internship project"})
    with OUTPUT.open("wb") as fh:
        writer.write(fh)
    print(f"wrote {OUTPUT} ({len(writer.pages)} pages; front matter from page {first_front + 1}, "
          f"Chapter 1 on page {first_main + 1}); work dir {work}")


if __name__ == "__main__":
    build()

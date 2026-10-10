"""Sanitized reproduction of the PDF structure Google Docs exports (Skia/PDF
renderer) — the layout that made pypdf's plain text extraction put a line break
between every word of a real resume.

Structure copied from the real file (content is entirely synthetic):
  * a page-level flipped coordinate system: ``1 0 0 -1 0 792 cm``;
  * every word drawn in its own ``q <scale/translate> cm BT ... Tm ... Tj ET Q``
    block, with the text matrix also flipped (``1 0 0 -1 0 0 Tm``);
  * two columns: the whole main column is drawn first, then the sidebar.
"""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def skia_style_pdf(main_column: list[str], sidebar: list[str], font_size: float = 11.0) -> bytes:
    """Each list item is one visual line; "" is paragraph spacing."""
    ops = ["1 0 0 -1 0 792 cm"]  # top-left origin, y grows downward (as Skia emits)

    glyph_advance = font_size * 0.55

    def text_object(x: float, text: str) -> str:
        # One BT per word (and per space), each resetting a flipped Tm and
        # positioned by "x -size Td", as Skia emits. (Skia also places each glyph
        # with its own Td; that detail is not what breaks pypdf, and a single Tj per
        # word keeps the fixture independent of exact font metrics.)
        return f"BT\n/F1 {font_size:g} Tf\n1 0 0 -1 0 -.288 Tm\n{x:.4f} {-font_size * 0.984:.4f} Td ({_escape(text)}) Tj\nET"

    def draw_column(lines: list[str], left: float) -> None:
        y = 60.0
        for line in lines:
            if line == "":
                y += font_size * 1.2
                continue
            ops.append(f"q\n.75 0 0 .75 {left:.2f} {y:.2f} cm")
            x = 0.0
            for index, word in enumerate(line.split(" ")):
                if index:
                    ops.append(text_object(x, " "))
                    x += glyph_advance
                ops.append(text_object(x, word))
                x += glyph_advance * len(word)
            ops.append("Q")
            y += font_size * 1.15

    draw_column(main_column, 40.0)
    draw_column(sidebar, 430.0)
    stream = "\n".join(ops).encode("cp1252")  # WinAnsiEncoding (em dash = 0x97)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode())
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(content)


# Sanitized stand-in for the observed resume: same layout pattern (wrapped inline
# tech annotations, an all-caps date line, all-caps wrapped certificates and
# languages in a sidebar), with every name and project replaced.
MAIN_COLUMN = [
    "SAMPLE PERSON", "Software Developer Aspirant", "sample.person@example.com", "",
    "EDUCATION", "", "Example Institute of Engineering And Technology,", "City — B.Tech Information Technology",
    "JUNE 2024 - JUNE 2028", "",
    "PROJECTS", "",
    "Community Ledger Portal — Built using Node,Express and", "MongoDB", "",
    "Developed a full-stack Community Ledger Portal independently", "using HTML, CSS, JavaScript, Node.js, Express.js, and MongoDB. The project",
    "was designed to manage members, payments, expenses and loans.", "",
    "Online Store Manager — Built using", "Html,Css,Javascript,React", "",
    "Developed an online store application using HTML, CSS, JavaScript,", "and React.js with product listing, cart management and checkout.",
]
SIDEBAR = [
    "SKILLS", "", "Frontend Development", "", "SQL Programming", "", "Object-Oriented Programming", "(OOP)", "",
    "ADDITIONAL", "", "ONLINE CERTIFIED IN JAVA", "PROGRAMME", "", "Completed Course on Data", "Visualization using Python", "",
    "LANGUAGES", "", "ENGLISH", "", "FRENCH",
]

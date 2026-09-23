"""A minimal, dependency-free PDF builder that draws one line of text per text-showing
operation with real Y-coordinate movement between lines — unlike the single-`Tj`-block
helper in test_pdf_extraction.py, this is close enough to how a real PDF layout engine
places text that pypdf's Y-coordinate-based line reconstruction (and therefore blank-line
detection) behaves the same way it would on a real resume PDF. Used for PDF/DOCX parity
tests: the same logical resume, both file types, should parse to materially the same
structure.
"""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_from_lines(lines: list[str], font_size: int = 11, line_height: float = 14.0, paragraph_gap: float = 22.0) -> bytes:
    ops = ["BT", f"/F1 {font_size} Tf", "72 740 Td"]
    pending_offset = 0.0
    first = True
    for line in lines:
        if line == "":
            pending_offset += paragraph_gap
            continue
        if first:
            move = pending_offset
            first = False
        else:
            move = pending_offset + line_height
        if move:
            ops.append(f"0 -{move:g} Td")
        ops.append(f"({_escape(line)}) Tj")
        pending_offset = 0.0
    ops.append("ET")
    stream = "\n".join(ops).encode()

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
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

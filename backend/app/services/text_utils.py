import re

# Bullet glyphs seen across PDF fonts (Symbol/Wingdings-style dingbats, typographic
# bullets, box/arrow markers). "-" is deliberately excluded: it is too overloaded
# with legitimate non-bullet uses (date ranges, name/subtitle separators) to safely
# rewrite at the raw-text layer; bullet detection for "-" happens structurally
# instead, in the section parsers that already know they are looking at a list.
_BULLET_GLYPHS = "•▪▫◦‣∙·●○□■◆➤➢➣☑✓✔"
_LEADING_BULLET_PATTERN = re.compile(rf"^([ \t]*)([{re.escape(_BULLET_GLYPHS)}]|[-])[ \t]*")
_PRIVATE_USE_OR_REPLACEMENT_PATTERN = re.compile(r"[-�]")


def _normalize_bullet_glyphs(text: str) -> str:
    """Rewrites the leading bullet marker of each line to a single canonical glyph.

    PDF extraction renders bullet characters inconsistently depending on the source
    font: some map to real Unicode bullet punctuation, others (Wingdings/Symbol-style
    fonts) map to unrecoverable Private Use Area code points. Collapsing every
    variant seen at the start of a line to "• " keeps downstream structural parsing
    (e.g. project/description grouping) from having to special-case each glyph.
    """
    lines = text.split("\n")
    normalized_lines = []
    for line in lines:
        match = _LEADING_BULLET_PATTERN.match(line)
        if match:
            leading_space = match.group(1)
            rest = line[match.end():]
            line = f"{leading_space}• {rest}"
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _strip_stray_private_use_characters(text: str) -> str:
    # Any Private Use Area or Unicode replacement characters remaining after bullet
    # normalization are unrecoverable font-glyph artifacts (or encoding failures);
    # they carry no real meaning, so they are dropped rather than left to reach
    # structured output or the UI as visible corruption (e.g. "").
    return _PRIVATE_USE_OR_REPLACEMENT_PATTERN.sub("", text)


def normalize_resume_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(character for character in normalized if character in "\n\t" or ord(character) >= 32)
    normalized = _normalize_bullet_glyphs(normalized)
    normalized = _strip_stray_private_use_characters(normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"[ ]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()

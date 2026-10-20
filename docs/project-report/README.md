# Academic Project Report — AI Career Companion

Academic project report for the Infosys internship project, written to complement (not replace)
the finalised technical documentation, `docs/FINAL_TECHNICAL_DOCUMENTATION.md`, which remains the
technical source of truth.

## Files

| Path | Content |
|---|---|
| `AI_Career_Companion_Project_Report.md` | Source of the report (authoritative text) |
| `AI_Career_Companion_Project_Report.docx` | Editable Word version (TOC, list of figures and list of tables filled by Word) |
| `AI_Career_Companion_Project_Report.pdf` | Rendered report, A4, 70 pages, with bookmarks and a clickable table of contents |
| `figures/*.svg`, `figures/*.png` | 11 diagrams and one chart (SVG sources, 2× PNG renders) |
| `figures/src/make_figures.py` | Generates the SVGs from facts verified in the repository |
| `figures/src/render_figures.ps1` | Renders the SVGs to PNG with headless Chrome |
| `tools/build_report.py` | Markdown → DOCX (python-docx) |
| `tools/update_docx_fields.ps1` | Fills the DOCX's Word fields (table of contents, lists, page numbers) |
| `tools/build_pdf.py` | Markdown → PDF (headless Chrome print, page numbers and header stamped with reportlab) |

## Regenerating (Windows, from the repository root)

```powershell
.venv\Scripts\python.exe docs\project-report\figures\src\make_figures.py
powershell -ExecutionPolicy Bypass -File docs\project-report\figures\src\render_figures.ps1
.venv\Scripts\python.exe docs\project-report\tools\build_report.py
powershell -ExecutionPolicy Bypass -File docs\project-report\tools\update_docx_fields.ps1
.venv\Scripts\python.exe docs\project-report\tools\build_pdf.py
```

Only already-installed tools are used: the project virtual environment (python-docx, reportlab,
pypdf, Pillow), Google Chrome and Microsoft Word. No new dependency was installed. The PDF is
rendered with Chrome rather than exported from Word because Word's PDF export stalled in this
environment, so the DOCX and PDF paginate differently (Word: 74 pages; PDF: 70 pages). Their
text, headings, captions, tables and figures are the same.

After editing the DOCX by hand (for example, to fill placeholders), update its fields in Word
(select all, then F9) so the table of contents and lists stay correct. Edits made only in the
DOCX are not carried back to the Markdown or the PDF.

## Placeholders to complete

Every placeholder is in square brackets and capitals:

- `[REGISTER NUMBER]`
- `[DEGREE NAME, e.g. BACHELOR OF TECHNOLOGY]` and `[DEGREE NAME]`
- `[DEPARTMENT]`
- `[COLLEGE / UNIVERSITY NAME]`, `[COLLEGE / UNIVERSITY ADDRESS]`
- `[PROJECT GUIDE NAME]`, `[HEAD OF DEPARTMENT NAME]`, `[INTERNSHIP SUPERVISOR NAME]`
- `[ACADEMIC YEAR]`, `[SUBMISSION DATE]`, `[VIVA DATE]`, `[PLACE]`

The certificate is a marked template; it must be issued and signed by the institution. The
declaration and acknowledgement are editable drafts for the student to verify. The student name
(Jeswin Jarald) and the internship organisation (Infosys) are taken from the finalised technical
documentation.

## Evidence used

- `docs/FINAL_TECHNICAL_DOCUMENTATION.md` (and its rendered PDF), `README.md`, `docs/MILESTONE_*.md`,
  `docs/RESUME_PARSING_AUDIT.md`, `docs/CAREER_OPPORTUNITY_GENERALIZATION.md`, `docs/file-purpose-guide.md`
- Source code: `backend/app` (routers, services, models, config), `src/App.tsx` and `src/config/api.ts` on `develop`
- Evaluation artifacts: `backend/data/evaluation/m4/results/` (M4.2 frozen baseline, M4.3 experiment log,
  optimisation report and final results), `backend/data/internships/` (dataset README and validation report),
  vector-store metadata
- `src/api/generated/openapi.json` (47 API operations)
- Re-runs on 2026-10-16 (outputs kept outside the repository): backend pytest suite (555 passed,
  1 xfailed, 2 warnings) and the M4 evaluation into a scratch directory; dataset SHA-1 and index metadata re-checked
- External references: only the publications and official documentation listed in the report's References

## Notes for reviewers

- The report describes the `develop` baseline. The checkout used to write it was the unmerged branch
  `feature/ui-redesign-skill-graph`, whose backend application code is identical to `develop`; its UI
  redesign and Playwright suite are mentioned (Section 7.12) but not described or evaluated.
- The 2026-10-16 evaluation re-run reproduced all retrieval, matching, consistency, conversation and
  discovery values and 0 grounding violations, but differed from the tracked M4.3 results in three
  grounding-related values (Section 7.8). This is reported, not corrected.
- No UI screenshots are included: none exist for the canonical baseline, and none were fabricated.

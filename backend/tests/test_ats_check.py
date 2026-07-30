"""The parse checks exist to answer one fear: will a machine garble this resume
before a human sees it. So the tests that matter prove the parse-critical
findings (multi-column scramble, contact stranded in a header, no email) are
CRITICAL, and that the safe cases stay quiet -- a false alarm here sends the
operator rewriting a resume that was already fine."""

import pytest

from lighthouse.track.ats_check import (
    AtsReport,
    Finding,
    Severity,
    _check_fonts,
    _check_glyphs,
    _check_sections,
    _find_gutter,
    _text_in_reading_order,
    build_parse_preview,
    check_resume,
    normalize_text_for_ligatures,
)

# US Letter in points, the geometry the checks reason about.
PAGE_W, PAGE_H = 612.0, 792.0


def _word(text: str, x0: float, x1: float, top: float) -> dict:
    """A pdfplumber-shaped word box with explicit geometry."""
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + 10}


def _two_column_words() -> list[dict]:
    """Twelve rows, a left word ending at x=240 and a right word starting at
    x=330 -- a clean vertical gutter no word crosses."""
    words: list[dict] = []
    for i in range(12):
        top = 120 + i * 40
        words.append(_word(f"left{i}", 90, 240, top))
        words.append(_word(f"right{i}", 330, 480, top))
    return words


def _single_column_words() -> list[dict]:
    """Full-width lines: every candidate gutter is crossed, so no column
    boundary exists."""
    return [_word(f"full-width-line-token-{i}", 72, 523, 120 + i * 25) for i in range(24)]


# --------------------------------------------------------------------------
# PDF builders (need reportlab + pdfplumber; guarded so the pure tests still
# run without them)
# --------------------------------------------------------------------------


def _single_column_pdf(path: str, *, contact_line: str, email_in_header: bool = False) -> None:
    pytest.importorskip("reportlab")
    pytest.importorskip("pdfplumber")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    _, height = letter
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 11)
    if email_in_header:
        # Top ~0.3in of the page -- above the header cutoff (page_height * 0.08).
        c.drawString(72, height - 0.3 * 72, "recruiter@x.com")
    y = height - 90  # first body line, comfortably below the header region
    c.drawString(72, y, "Jane Doe")
    if contact_line:
        y -= 16
        c.drawString(72, y, contact_line)
    y -= 40
    c.drawString(72, y, "Experience")
    for line in [
        "Software Engineer Intern, Acme Corporation  Jun 2025 - Present",
        "- Built distributed services in Python and Go for high scale",
        "- Scaled backend systems to millions of daily active users",
        "- Automated CI deployment and cut p99 latency substantially",
    ]:
        y -= 16
        c.drawString(72, y, line)
    y -= 24
    c.drawString(72, y, "Skills")
    y -= 16
    c.drawString(72, y, "Python, Go, Kubernetes, Docker, SQL, PostgreSQL, Redis")
    y -= 24
    c.drawString(72, y, "Education")
    y -= 16
    c.drawString(72, y, "B.S. Computer Science, University of Texas at Austin  2028")
    c.showPage()
    c.save()


def _two_column_pdf(path: str) -> None:
    pytest.importorskip("reportlab")
    pytest.importorskip("pdfplumber")
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    _, height = letter
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 11)
    left = ["Skills", "Python", "Golang", "Kubernetes", "Docker",
            "SQL", "Redis", "Kafka", "Linux", "AWS"]  # fmt: skip
    right = ["Experience", "Engineer at Acme", "Built services", "Scaled systems",
             "Led migration", "Reduced latency", "Shipped features",
             "Mentored interns", "On call rotation", "Owned uptime"]  # fmt: skip
    y = height - 100
    for left_word, right_word in zip(left, right, strict=True):
        c.drawString(1 * inch, y, left_word)  # left column at x = 1in
        c.drawString(4.2 * inch, y, right_word)  # right column at x = 4.2in
        y -= 20
    c.showPage()
    c.save()


class TestCheckResumePdf:
    def test_clean_single_column_parses_cleanly(self, tmp_path):
        """A single column with contact in the body, standard headings and a
        safe font is exactly what the ATS is built to read."""
        path = str(tmp_path / "clean.pdf")
        _single_column_pdf(path, contact_line="email@x.com | (512) 555-0199")
        report = check_resume(path)

        assert report.will_parse_cleanly is True
        assert report.critical == []
        assert report.preview.column_count == 1
        assert report.preview.scrambled is False
        assert report.fonts == ["Helvetica"]

    def test_two_column_layout_is_critical(self, tmp_path):
        """Two columns read straight across interleave into nonsense -- the most
        dangerous and most common parse failure."""
        path = str(tmp_path / "two.pdf")
        _two_column_pdf(path)
        report = check_resume(path)

        layout = [f for f in report.critical if f.category == "layout"]
        assert layout, "expected a CRITICAL layout finding"
        assert report.preview.column_count == 2
        assert report.preview.scrambled is True

    def test_contact_in_header_is_critical(self, tmp_path):
        """An email that lives only in the header is dropped by ~a quarter of
        systems, leaving no way to reach the candidate."""
        path = str(tmp_path / "header.pdf")
        _single_column_pdf(path, contact_line="", email_in_header=True)
        report = check_resume(path)

        contact = [f for f in report.critical if f.category == "contact"]
        assert contact, "expected a CRITICAL contact finding"
        assert any("header" in (f.title + f.detail).lower() for f in contact)

    def test_no_email_is_critical(self, tmp_path):
        """No extractable email means the ATS cannot build a candidate record."""
        path = str(tmp_path / "noemail.pdf")
        _single_column_pdf(path, contact_line="Austin, Texas")
        report = check_resume(path)

        assert any(
            f.category == "contact" and "No email address found" in f.title for f in report.critical
        )

    def test_unreadable_file_reports_extraction_not_raise(self, tmp_path):
        """A file that is not a real PDF is itself a finding, never an
        exception the caller has to catch."""
        path = tmp_path / "broken.pdf"
        path.write_bytes(b"not a pdf")
        report = check_resume(str(path))

        assert any(f.category == "extraction" for f in report.critical)


class TestSortedFindings:
    def test_severities_are_non_increasing(self):
        """sorted_findings surfaces the parse-killers first, whatever order they
        were appended in."""
        report = AtsReport(
            findings=[
                Finding(Severity.MINOR, "dates", "m", "d", "f"),
                Finding(Severity.CRITICAL, "layout", "c", "d", "f"),
                Finding(Severity.WARNING, "fonts", "w", "d", "f"),
            ]
        )
        severities = [f.severity for f in report.sorted_findings()]

        assert severities == sorted(severities, reverse=True)
        assert severities[0] is Severity.CRITICAL


class TestParsePreview:
    def test_two_columns_are_scrambled(self):
        """Side-by-side columns disagree with the naive left-to-right read, which
        is the concrete demonstration of the scramble."""
        preview = build_parse_preview(_two_column_words(), PAGE_W, PAGE_H)
        assert preview.column_count == 2
        assert preview.scrambled is True

    def test_single_column_is_clean(self):
        """One column reads the same either way, so nothing is flagged."""
        preview = build_parse_preview(_single_column_words(), PAGE_W, PAGE_H)
        assert preview.column_count == 1
        assert preview.scrambled is False


class TestGutter:
    def test_gutter_found_between_columns(self):
        gutter = _find_gutter(_two_column_words(), PAGE_W, PAGE_H)
        assert gutter is not None
        assert 240 <= gutter <= 330

    def test_no_gutter_in_single_column(self):
        assert _find_gutter(_single_column_words(), PAGE_W, PAGE_H) is None

    def test_naive_read_interleaves_columns(self):
        """The naive read pulls a left and a right word onto the same line --
        the interleaving a simple parser produces."""
        first_line = _text_in_reading_order(_two_column_words()).splitlines()[0]
        assert "left0" in first_line and "right0" in first_line


class TestGlyphChecks:
    @pytest.mark.parametrize(
        ("text", "title_substr"),
        [
            ("this is efﬁcient work here", "Ligature"),
            ("▪ delivered a project on time", "bullet"),
        ],
    )
    def test_risky_characters_warn(self, text, title_substr):
        findings = _check_glyphs(text)
        assert any(
            f.severity is Severity.WARNING and title_substr.lower() in f.title.lower()
            for f in findings
        )

    def test_clean_text_has_no_findings(self):
        assert _check_glyphs("Clean resume text with ordinary words only") == []


class TestFontChecks:
    @pytest.mark.parametrize(
        ("fonts", "expect_warning"),
        [
            (["Montserrat-Bold"], True),  # design font absent from ATS servers
            (["ArialMT"], False),  # a universally safe face
        ],
    )
    def test_non_ats_fonts_warn(self, fonts, expect_warning):
        findings = _check_fonts(fonts)
        has_warning = any(
            f.severity is Severity.WARNING and f.category == "fonts" for f in findings
        )
        assert has_warning is expect_warning


class TestSectionChecks:
    def test_nonstandard_headings_warn(self):
        """When every heading is bespoke, the ATS cannot map content to the
        fields recruiters filter on."""
        text = "What I've Built\nMy Journey\nToolbox\nSide Quests\n"
        finding = _check_sections(text)
        assert finding is not None
        assert finding.severity is Severity.WARNING
        assert finding.category == "sections"

    def test_standard_headings_pass(self):
        assert _check_sections("Experience\nSkills\nEducation\n") is None


class TestLigatureNormalization:
    def test_expands_ligature_so_keyword_survives(self):
        """A ligature-corrupted word must still match the plain keyword."""
        assert "efficiency" in normalize_text_for_ligatures("eﬃciency")


class TestVerdict:
    @pytest.mark.parametrize(
        ("finding", "substr"),
        [
            (Finding(Severity.CRITICAL, "layout", "t", "d", "f"), "auto-reject"),
            (Finding(Severity.WARNING, "fonts", "t", "d", "f"), "Should parse"),
        ],
    )
    def test_verdict_reflects_worst_finding(self, finding, substr):
        assert substr in AtsReport(findings=[finding]).verdict()

    def test_empty_report_is_a_clean_parse(self):
        assert "Clean parse" in AtsReport().verdict()

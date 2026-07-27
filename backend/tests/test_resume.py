"""Resume extraction produces drafts the operator corrects, so a wrong split is
cheap but a lost or invented line is not. These tests pin the section routing and
the one heading heuristic that has already regressed once."""

import pytest

from lighthouse.core.resume import ExtractedResume, facts_from_text

RESUME = """Jane Doe
jane@example.com | 555-0100

Experience
Software Engineer Intern, Acme — Jun 2025
- Built distributed services in Python
- Scaled systems to millions of users

Projects
Realtime Chat — 2024
- Messaging over WebSockets

Skills
Python, Go, Kubernetes | Docker, SQL

Education
B.S. Computer Science, UT — 2028
Coursework: algorithms, data structures, operating systems, databases
"""


@pytest.fixture
def facts():
    return facts_from_text(RESUME)


class TestSectionRouting:
    @pytest.mark.parametrize(
        ("fact_type", "title_prefix"),
        [
            ("experience", "Software Engineer Intern"),
            ("project", "Realtime Chat"),
            ("education", "B.S."),
        ],
    )
    def test_sections_map_to_fact_types(self, facts, fact_type, title_prefix):
        titles = [f.title for f in facts if f.fact_type == fact_type]
        assert any(t.startswith(title_prefix) for t in titles)

    def test_preamble_is_skipped(self, facts):
        """The name and contact line come before any header and carry no fact."""
        titles = [f.title for f in facts]
        assert "Jane Doe" not in titles
        assert not any("jane@example.com" in t for t in titles)


class TestEducationRegression:
    def test_titled_entry_without_bullets_keeps_its_title(self, facts):
        """A degree line with a year but no bullets once became "Untitled"; it
        must keep its own title."""
        education = [f for f in facts if f.fact_type == "education"]
        assert any(f.title.startswith("B.S.") for f in education)
        assert not any(f.title == "Untitled" for f in education)

    def test_coursework_enumeration_is_body_not_heading(self, facts):
        """A line with several commas is content, not a new entry."""
        degree = next(f for f in facts if f.title.startswith("B.S."))
        assert "algorithms" in degree.body
        titles = [f.title for f in facts]
        assert not any(t.startswith("Coursework") for t in titles)


class TestSkills:
    def test_split_into_individual_facts(self, facts):
        skills = {f.title for f in facts if f.fact_type == "skill"}
        assert {"Python", "Go", "Kubernetes", "Docker", "SQL"} <= skills

    def test_each_skill_has_no_body(self, facts):
        skills = [f for f in facts if f.fact_type == "skill"]
        assert all(f.body == "" for f in skills)


class TestExtractedResume:
    def test_text_construction_has_no_image_flag(self):
        """facts_from_text is text-only; the image flag is set by extract_pdf."""
        assert ExtractedResume().likely_image_based is False


class TestExtractPdf:
    def test_text_pdf_extracts_facts_and_is_not_image_based(self, tmp_path):
        """A selectable-text resume yields facts and is not flagged as an image."""
        reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
        pytest.importorskip("pdfplumber")
        from lighthouse.core.resume import extract_pdf

        path = tmp_path / "resume.pdf"
        pdf = reportlab_canvas.Canvas(str(path))
        lines = [
            "Experience",
            "Software Engineer Intern, Acme 2025",
            "- Built distributed systems in Python and Go",
            "- Scaled services to millions of requests per day",
            "Skills",
            "Python, Go, Kubernetes, Docker",
        ]
        y = 740
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 20
        pdf.save()

        result = extract_pdf(str(path))
        assert result.char_count > 100
        assert result.likely_image_based is False
        assert {f.fact_type for f in result.facts} >= {"experience", "skill"}

    def test_textless_pdf_is_flagged_image_based(self, tmp_path):
        """Under 100 characters from a page almost always means a scanned image,
        which an ATS could not read either."""
        reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
        pytest.importorskip("pdfplumber")
        from lighthouse.core.resume import extract_pdf

        path = tmp_path / "blank.pdf"
        pdf = reportlab_canvas.Canvas(str(path))
        pdf.showPage()
        pdf.save()

        result = extract_pdf(str(path))
        assert result.page_count >= 1
        assert result.likely_image_based is True

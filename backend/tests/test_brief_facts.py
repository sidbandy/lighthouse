"""Facts pulled from a description, and the two ways that goes wrong.

Both cases here were found by running the extractor over real postings rather
than by reading it. A pattern matching "thrives under tight deadlines" reports a
soft-skills bullet as this posting's closing date; a GPA pattern with no bound
reports "8.00" -- a ten-point scale -- beside US postings on a four-point one.
Each produces a confident, checkable-looking fact that is simply wrong, which is
worse than extracting nothing.
"""

from lighthouse.discover.brief import build


def _brief(text: str):
    return build(text)


class TestDeadline:
    def test_reads_a_real_application_deadline(self):
        b = _brief("Application Deadline: Friday, 28th August 2026.")
        assert b.deadline is not None
        assert "28th August" in b.deadline.value

    def test_reads_apply_by_phrasing(self):
        b = _brief("Please apply by 15 March 2027 to be considered.")
        assert b.deadline is not None

    def test_reads_deadline_to_apply(self):
        b = _brief("The deadline to apply for this opportunity is Friday, July 31.")
        assert b.deadline is not None

    def test_ignores_deadlines_as_a_soft_skill(self):
        """The false positive that made this field untrustworthy: a large
        minority of postings say something like this in their responsibilities,
        and none of them are stating a closing date."""
        for sentence in (
            "You work well under tight deadlines and juggle competing priorities.",
            "We move fast, hit our deadlines, and focus on how we can deliver.",
            "Manage project workflows and deadlines across multi-channel campaigns.",
        ):
            assert _brief(sentence).deadline is None

    def test_says_nothing_when_the_posting_says_nothing(self):
        assert _brief("We are hiring a software engineering intern.").deadline is None


class TestGpa:
    def test_reads_a_stated_floor(self):
        b = _brief("Candidates must have a GPA of 3.0 or above.")
        assert b.gpa is not None and b.gpa.value == "3.0"

    def test_reads_the_trailing_form(self):
        b = _brief("Minimum 3.5 GPA required.")
        assert b.gpa is not None and b.gpa.value == "3.5"

    def test_drops_an_out_of_scale_figure(self):
        """A ten-point scale rendered as a GPA requirement beside four-point
        postings invites exactly the wrong conclusion, and the posting never
        said which scale it meant, so converting would be inventing."""
        assert _brief("Student with a current GPA of 8.00 in Computer Science.").gpa is None

    def test_keeps_the_evidence_sentence(self):
        b = _brief("Applicants need a cumulative GPA of 3.2 to qualify.")
        assert b.gpa is not None
        assert "3.2" in b.gpa.evidence


class TestProratedPay:
    def test_adds_a_second_reading_of_an_annualised_intern_salary(self):
        """Quant firms quote interns an annualised base. The extraction is
        correct and reads as absurd, so the term figure goes beside it."""
        b = _brief(
            "The base salary for this position is $250,000 per year. "
            "This is a 10 week summer internship."
        )
        assert b.compensation is not None
        assert b.compensation.value.startswith("$250,000 per year")
        assert "~$48k over 10 weeks" in b.compensation.value

    def test_never_replaces_the_stated_figure(self):
        b = _brief("Base salary is $300,000 per year. The program runs 9 weeks.")
        assert "$300,000 per year" in b.compensation.value

    def test_leaves_hourly_pay_alone(self):
        b = _brief("Compensation is $45.00 per hour. The internship runs for 12 weeks.")
        assert b.compensation.value == "$45.00 per hour"

    def test_does_nothing_without_a_stated_length(self):
        """Both halves have to come from the posting. Assuming ten weeks would
        be inventing the number the whole line exists to avoid."""
        b = _brief("The annual base salary is $120,000.")
        assert b.compensation.value == "$120,000 per year"

    def test_ignores_a_length_that_is_not_weeks(self):
        b = _brief("Base salary $200,000 per year. This is a 6 month placement.")
        assert "over" not in b.compensation.value

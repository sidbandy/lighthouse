"""Study: the pattern record, the ladder, and the review schedule.

The spec asked for a decayed mastery score with a Bayesian cold-start prior.
Both are overruled by the no-invented-numbers rule, so what has to be tested
instead is that the honest substitutes hold: that a thin record says it is thin
rather than producing a confident fraction, that a pattern with nothing logged
is treated as unmeasured rather than as weak, and that the review queue never
grows a backlog no matter how long someone is away.

That last one is the whole reason anyone still uses a study tool in week six,
and it is tested by simulating an actual absence rather than by reading the cap.
"""

from datetime import UTC, date, datetime, timedelta
from random import Random
from types import SimpleNamespace
from uuid import uuid4

import pytest

from lighthouse.core.corpus import COMPETENCIES
from lighthouse.practice import questions
from lighthouse.study import catalog, srs
from lighthouse.study.attempts import (
    MIN_ATTEMPTS,
    RECENT_WINDOW,
    Outcome,
    PatternRecord,
)
from lighthouse.study.company_delta import HALF_LIFE_MONTHS, recency_weight

TODAY = date(2026, 9, 1)
_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _attempt(outcome: str, days_ago: int, slug: str = "two-sum"):
    return SimpleNamespace(
        problem_slug=slug,
        outcome=outcome,
        attempted_at=_NOW - timedelta(days=days_ago),
        pattern_tags=["arrays_hashing"],
    )


def _record(*attempts) -> PatternRecord:
    ordered = sorted(attempts, key=lambda a: a.attempted_at, reverse=True)
    return PatternRecord(pattern=catalog.PATTERNS[0], attempts=list(ordered))


class TestPatternRecord:
    def test_nothing_logged_is_untouched_not_weak(self):
        """Different problems with different answers: one needs practice, the
        other needs a first attempt."""
        record = _record()
        assert record.is_untouched
        assert not record.is_weak
        assert record.statement(TODAY) == "No attempts yet."

    def test_a_thin_record_refuses_to_read_as_evidence(self):
        record = _record(_attempt(Outcome.FAILED, 1), _attempt(Outcome.FAILED, 2))
        assert record.total < MIN_ATTEMPTS
        assert not record.is_weak
        assert "too few to read anything into" in record.statement(TODAY)

    def test_a_real_sample_of_failures_reads_as_weak(self):
        record = _record(*[_attempt(Outcome.FAILED, i) for i in range(1, 5)])
        assert record.is_weak
        assert "0 of 4 clean" in record.statement(TODAY)

    def test_mostly_clean_is_not_weak(self):
        record = _record(
            _attempt(Outcome.SOLVED_CLEAN, 1),
            _attempt(Outcome.SOLVED_CLEAN, 2),
            _attempt(Outcome.FAILED, 3),
        )
        assert not record.is_weak

    def test_the_record_is_read_over_a_window(self):
        """A search runs for months. Last spring is not evidence about today."""
        old = [_attempt(Outcome.FAILED, 200 + i) for i in range(10)]
        new = [_attempt(Outcome.SOLVED_CLEAN, i) for i in range(1, 4)]
        record = _record(*old, *new)
        assert record.total == RECENT_WINDOW
        assert record.clean == 3

    def test_it_reports_when_you_last_touched_it(self):
        record = _record(_attempt(Outcome.SOLVED_CLEAN, 9))
        assert record.days_since(TODAY) == 9
        assert "last 9 days ago" in record.statement(TODAY)

    def test_no_score_appears_anywhere(self):
        record = _record(*[_attempt(Outcome.SOLVED_CLEAN, i) for i in range(1, 5)])
        statement = record.statement(TODAY)
        assert "%" not in statement
        assert "mastery" not in statement.lower()


class TestLadder:
    def test_a_clean_solve_advances_one_step(self):
        assert srs._step_for([Outcome.SOLVED_CLEAN]) == 1
        assert srs._step_for([Outcome.SOLVED_CLEAN] * 3) == 3

    def test_a_failure_returns_to_the_start(self):
        assert srs._step_for([Outcome.SOLVED_CLEAN] * 3 + [Outcome.FAILED]) == 0

    def test_a_hint_holds_rather_than_punishing_honesty(self):
        """The operator is the only person logging these. Dropping to zero for
        admitting a hint teaches them to stop admitting it."""
        assert srs._step_for([Outcome.SOLVED_CLEAN] * 3 + [Outcome.SOLVED_WITH_HINT]) == 2

    def test_the_ladder_has_a_ceiling(self):
        assert srs._step_for([Outcome.SOLVED_CLEAN] * 50) == len(srs.INTERVALS) - 1


class _Session:
    """Just enough of a Session for the queue builder, which only reads."""

    def __init__(self, attempts):
        self._attempts = attempts

    def scalars(self, _stmt):
        return sorted(self._attempts, key=lambda a: a.attempted_at)


def _queue(attempts, today=TODAY, cap=srs.DAILY_CAP):
    return srs.build_queue(
        _Session(attempts), today=today, cap=cap, user_id=uuid4()
    )


class TestReviewQueue:
    def test_nothing_logged_means_nothing_to_review(self):
        queue = _queue([])
        assert queue.due == [] and queue.upcoming == []
        assert "Nothing to review yet" in queue.note()

    def test_a_clean_solve_comes_back_after_its_interval(self):
        queue = _queue([_attempt(Outcome.SOLVED_CLEAN, 5, "two-sum")])
        # step 1 -> 3-day interval, solved 5 days ago, so it is due.
        assert [r.problem_slug for r in queue.due] == ["two-sum"]

    def test_a_fresh_solve_is_not_due_yet(self):
        queue = _queue([_attempt(Outcome.SOLVED_CLEAN, 0, "two-sum")])
        assert queue.due == []
        assert [r.problem_slug for r in queue.upcoming] == ["two-sum"]
        assert "Nothing due today" in queue.note()

    def test_a_long_absence_never_produces_a_backlog(self):
        """The failure mode this whole module is shaped around: coming back to
        "47 due" is the moment people close the tab for good."""
        attempts = [
            _attempt(Outcome.SOLVED_CLEAN, 300, f"problem-{i}") for i in range(40)
        ]
        queue = _queue(attempts)
        assert len(queue.due) == srs.DAILY_CAP
        assert queue.total_due == 40
        assert queue.was_capped
        # The note must read as a normal day's work, not as a debt.
        assert "not stacked on top of you" in queue.note()

    def test_most_decayed_surfaces_first(self):
        """A one-day interval three days late has lost more than a ninety-day
        interval three days late."""
        attempts = [
            _attempt(Outcome.FAILED, 4, "just-failed"),
            *[_attempt(Outcome.SOLVED_CLEAN, 95 - i, "long-interval") for i in range(6)],
        ]
        queue = _queue(attempts)
        assert queue.due[0].problem_slug == "just-failed"

    def test_a_gap_does_not_reset_progress(self):
        """The schedule slid; the knowledge did not evaporate."""
        attempts = [_attempt(Outcome.SOLVED_CLEAN, 200 - i * 10, "two-sum") for i in range(4)]
        queue = _queue(attempts)
        assert queue.due[0].step == 4

    def test_the_cap_is_respected_exactly(self):
        attempts = [_attempt(Outcome.FAILED, 30, f"p-{i}") for i in range(20)]
        assert len(_queue(attempts, cap=5).due) == 5


class TestRecencyWeighting:
    def test_a_recent_report_outweighs_an_old_one(self):
        """Companies rotate their question pools. A 2023 report is history."""
        recent = recency_weight(TODAY - timedelta(days=30), today=TODAY)
        old = recency_weight(TODAY - timedelta(days=730), today=TODAY)
        assert recent > old * 5

    def test_the_half_life_is_where_it_says_it_is(self):
        at_half_life = recency_weight(
            TODAY - timedelta(days=int(HALF_LIFE_MONTHS * 30.44)), today=TODAY
        )
        assert 0.34 < at_half_life < 0.38

    def test_an_undated_report_counts_least(self):
        assert recency_weight(None) < recency_weight(TODAY, today=TODAY)


class TestCatalogIntegrity:
    """The catalogue is hand-maintained, so the things a typo would break are
    checked rather than assumed."""

    def test_every_problem_names_a_real_pattern(self):
        for problem in catalog.PROBLEMS:
            for slug in problem.patterns:
                assert slug in catalog.PATTERNS_BY_SLUG, f"{problem.slug} -> {slug}"

    def test_every_prerequisite_is_a_real_pattern(self):
        for pattern in catalog.PATTERNS:
            for slug in pattern.prerequisites:
                assert slug in catalog.PATTERNS_BY_SLUG, f"{pattern.slug} -> {slug}"

    def test_prerequisites_do_not_cycle(self):
        for pattern in catalog.PATTERNS:
            seen, queue = set(), list(pattern.prerequisites)
            while queue:
                slug = queue.pop()
                assert slug != pattern.slug, f"{pattern.slug} requires itself"
                if slug in seen:
                    continue
                seen.add(slug)
                queue.extend(catalog.PATTERNS_BY_SLUG[slug].prerequisites)

    def test_every_pattern_has_somewhere_to_practise(self):
        for pattern in catalog.PATTERNS:
            assert pattern.resources, f"{pattern.slug} has no resource"

    def test_every_topic_has_a_route_and_a_trigger(self):
        for topic in catalog.TOPICS:
            assert topic.triggers, f"{topic.slug} can never fire"
            assert topic.resources, f"{topic.slug} says what to learn but not where"

    def test_triggers_are_specific_enough_to_mean_something(self):
        """Single common words fire on unrelated postings. "training" in an
        aerospace listing is employee training, and recommending an ML course
        off it is a wrong answer delivered confidently."""
        too_generic = {
            "model", "training", "metrics", "strategy", "architecture",
            "database", "queries", "threads", "parallel", "async", "trading",
            "linux", "networking", "embedded", "quantitative", "statistics",
        }
        for topic in catalog.TOPICS:
            for trigger in topic.triggers:
                assert trigger not in too_generic, f"{topic.slug}: {trigger!r} is too generic"

    def test_every_pattern_has_at_least_one_problem(self):
        for pattern in catalog.PATTERNS:
            assert catalog.problems_for(pattern.slug), f"{pattern.slug} has no problems"

    def test_problem_slugs_are_unique(self):
        slugs = [p.slug for p in catalog.PROBLEMS]
        assert len(slugs) == len(set(slugs))


class TestQuestionBank:
    def test_it_prefers_a_competency_with_no_story(self):
        """Practising the one you already have a polished story for feels good
        and teaches nothing."""
        chosen = questions.pick(uncovered_competencies=["conflict"], rng=Random(0))
        assert chosen.competency == "conflict"

    def test_every_question_carries_a_follow_up(self):
        assert all(q.follow_up.strip() for q in questions.QUESTIONS)

    def test_it_does_not_repeat_within_a_session(self):
        asked = [q.text for q in questions.QUESTIONS_BY_COMPETENCY["conflict"]]
        chosen = questions.pick(
            uncovered_competencies=["conflict"], exclude=asked, rng=Random(0)
        )
        assert chosen.text not in asked

    @pytest.mark.parametrize("competency", sorted(questions.QUESTIONS_BY_COMPETENCY))
    def test_every_competency_has_more_than_one_question(self, competency):
        assert len(questions.QUESTIONS_BY_COMPETENCY[competency]) >= 2

    def test_the_bank_covers_the_corpus_competencies(self):
        """A competency the story bank tracks but no question exercises is a
        gap the operator can never close by practising."""
        tracked = {slug for slug, _ in COMPETENCIES}
        assert tracked <= set(questions.QUESTIONS_BY_COMPETENCY)

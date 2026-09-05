"""Dedup is the reason the posting/source split exists, and it had no tests.

The module documents four rules in a deliberate order -- block by company,
veto on a job-id disagreement, merge on canonical URL, then fuzzy title. These
pin each of them, plus the merge-field rules and determinism, so that a change
to one rule fails here rather than quietly changing what the operator sees.

The bias throughout is that a false merge is worse than a false split: merging
two real roles hides a job the operator can never find again, while a
near-duplicate is something they can dismiss."""

from datetime import UTC, datetime

from lighthouse.ingest.base import RawPosting
from lighthouse.ingest.dedup import deduplicate


def raw(
    *,
    source_id="src-a",
    company="Optiver",
    title="Software Engineer Intern",
    url="https://boards.greenhouse.io/optiver/jobs/1000001",
    **kwargs,
) -> RawPosting:
    return RawPosting(
        source_id=source_id, company_name=company, title=title, url=url, **kwargs
    )


def titles(merged) -> set[str]:
    return {m.title for m in merged}


class TestBlocking:
    def test_two_companies_never_merge(self):
        """Blocking by company is what keeps the work linear, and what stops
        'Software Engineer Intern' collapsing across the whole market."""
        merged = deduplicate(
            [
                raw(company="Optiver", url="https://a.test/1"),
                raw(company="Jane Street", url="https://b.test/1"),
            ]
        )

        assert len(merged) == 2


class TestJobIdVeto:
    def test_different_job_ids_do_not_merge(self):
        merged = deduplicate(
            [
                raw(url="https://boards.greenhouse.io/optiver/jobs/1000001"),
                raw(url="https://boards.greenhouse.io/optiver/jobs/2000002"),
            ]
        )

        assert len(merged) == 2

    def test_the_veto_beats_an_identical_title(self):
        """Checked before anything fuzzy, on purpose: two genuinely different
        roles at one company routinely share a title."""
        merged = deduplicate(
            [
                raw(title="Software Engineer Intern", url="https://boards.greenhouse.io/optiver/jobs/1111111"),
                raw(title="Software Engineer Intern", url="https://boards.greenhouse.io/optiver/jobs/2222222"),
            ]
        )

        assert len(merged) == 2

    def test_same_job_id_merges_across_sources(self):
        merged = deduplicate(
            [
                raw(source_id="simplify", url="https://boards.greenhouse.io/optiver/jobs/1111111"),
                raw(source_id="vansh", url="https://boards.greenhouse.io/optiver/jobs/1111111?utm=x"),
            ]
        )

        assert len(merged) == 1
        assert merged[0].source_count == 2


class TestCanonicalUrl:
    def test_tracking_parameters_do_not_split_a_posting(self):
        merged = deduplicate(
            [
                raw(source_id="a", url="https://careers.test/job/9"),
                raw(source_id="b", url="https://careers.test/job/9?utm_source=x&gh_src=y"),
            ]
        )

        assert len(merged) == 1


class TestFuzzyTitle:
    def test_near_identical_titles_merge(self):
        merged = deduplicate(
            [
                raw(title="Software Engineer Intern", url="https://x.test/1"),
                raw(title="Software Engineer, Intern", url="https://x.test/2"),
            ]
        )

        assert len(merged) == 1

    def test_clearly_different_titles_do_not(self):
        merged = deduplicate(
            [
                raw(title="Software Engineer Intern", url="https://x.test/1"),
                raw(title="Mechanical Design Engineer Intern", url="https://x.test/2"),
            ]
        )

        assert len(merged) == 2


class TestMergedFields:
    def test_keeps_earliest_date_longest_description_and_all_sources(self):
        early = datetime(2026, 8, 1, tzinfo=UTC)
        late = datetime(2026, 9, 1, tzinfo=UTC)
        merged = deduplicate(
            [
                raw(
                    source_id="a",
                    url="https://x.test/job/1",
                    description="Short.",
                    posted_at=late,
                    locations_raw=["Austin, TX"],
                ),
                raw(
                    source_id="b",
                    url="https://x.test/job/1?utm=1",
                    description="A considerably longer description with detail.",
                    posted_at=early,
                    locations_raw=["New York, NY"],
                ),
            ]
        )

        (one,) = merged
        assert one.posted_at == early
        assert one.description == "A considerably longer description with detail."
        assert one.source_ids == ["a", "b"]
        assert len(one.locations) == 2

    def test_prefers_the_longest_company_spelling(self):
        """Only reachable because the two spellings now land in one posting;
        before the cross-block fold they were separate rows and the display
        name depended on which block sorted first."""
        merged = deduplicate(
            [
                raw(source_id="a", company="Jump", url="https://x.test/job/1"),
                raw(
                    source_id="b",
                    company="Jump Trading Group",
                    url="https://x.test/job/1?utm_source=feed",
                ),
            ]
        )

        assert len(merged) == 1
        assert merged[0].company_name == "Jump Trading Group"


class TestDeterminism:
    def test_input_order_does_not_change_the_output(self):
        """The run-over-run diff behind new-posting alerts is only meaningful
        if the same input always produces the same grouping."""
        rows = [
            raw(source_id="a", company="Optiver", url="https://x.test/job/1"),
            raw(source_id="b", company="Jane Street", url="https://y.test/job/2"),
            raw(source_id="c", company="Optiver", url="https://x.test/job/1?utm=1"),
        ]

        assert titles(deduplicate(rows)) == titles(deduplicate(list(reversed(rows))))
        assert len(deduplicate(rows)) == len(deduplicate(list(reversed(rows))))


class TestCompanySpellingSplit:
    def test_one_url_is_one_posting_across_company_spellings(self):
        """Found live: 59 canonical URLs claimed by two merged postings each.

        Akuna lists the same job under 'Akuna Capital' on some feeds and
        'Akuna Capital University' on others. Blocking by company means the two
        are never compared, so one job -- same URL, same gh_jid -- became two
        postings, two cards in a lane, and two rows racing for one unique
        canonical_url on write."""
        merged = deduplicate(
            [
                raw(
                    source_id="speedyapply",
                    company="Akuna Capital",
                    url="https://akunacapital.com/careers/job/8018886?gh_jid=8018886",
                ),
                raw(
                    source_id="simplify",
                    company="Akuna Capital University",
                    url="https://akunacapital.com/careers/job/8018886?gh_jid=8018886",
                ),
            ]
        )

        assert len(merged) == 1
        assert merged[0].source_count == 2

    def test_different_urls_still_do_not_merge_across_companies(self):
        """The cross-company fold is keyed on the URL alone. Nothing else may
        leak across the company block, or the blocking rule is gone."""
        merged = deduplicate(
            [
                raw(company="Akuna Capital", url="https://akunacapital.com/careers/job/1"),
                raw(company="Akuna Capital University", url="https://akunacapital.com/careers/job/2"),
            ]
        )

        assert len(merged) == 2

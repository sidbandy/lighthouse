"""On-demand description fetching.

Roughly 19 in 20 active postings are title-only, which is why the Target lane
stays near-empty: it will not call a match realistic without a real
description. This covers the one posting the operator has actually opened.

Because it reaches a third-party host on the operator's behalf, the rules that
matter most here are the ones about restraint and honesty: robots.txt decides,
and a page that yields boilerplate produces "nothing readable" rather than a
short description. A wrong description is worse than none -- it feeds match
scoring, the tailor and the brief, and the operator would never know."""

import httpx
import pytest

from lighthouse.discover import description as desc

REAL_DESCRIPTION = (
    "<h2>Software Engineer Intern</h2><p>You will work on distributed systems in Python "
    "and Go, building services that process millions of events per day. </p>"
    "<ul><li>Strong fundamentals in data structures and algorithms</li>"
    "<li>Experience with Python, Go or Rust</li>"
    "<li>Currently pursuing a BS or MS in Computer Science</li></ul>"
    "<p>We run a two-stage interview: an online assessment followed by two technical "
    "rounds with engineers on the team. Compensation is $9,000 per month plus housing. "
    "This is a twelve week programme running from June through August. </p>"
) * 2


@pytest.fixture(autouse=True)
def clear_robots_cache():
    desc._robots.clear()
    yield
    desc._robots.clear()


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def responder(*, robots: str = "", page: str = REAL_DESCRIPTION, status: int = 200,
              content_type: str = "text/html", robots_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(robots_status, text=robots)
        return httpx.Response(status, text=page, headers={"content-type": content_type})

    return handler


class TestRobots:
    def test_a_disallow_is_a_refusal_not_an_obstacle(self):
        handler = responder(robots="User-agent: *\nDisallow: /jobs/")
        text, result = desc.fetch_description(
            "https://acme.test/jobs/1", client=client_for(handler)
        )

        assert text is None
        assert result.ok is False
        assert "robots.txt" in result.reason

    def test_an_allow_is_honoured(self):
        handler = responder(robots="User-agent: *\nDisallow: /admin/")
        text, result = desc.fetch_description(
            "https://acme.test/jobs/1", client=client_for(handler)
        )

        assert result.ok is True
        assert text and "distributed systems" in text

    def test_no_robots_file_is_permission(self):
        """The standard's own default. A 404 means nothing was forbidden."""
        handler = responder(robots_status=404)
        _, result = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert result.ok is True

    def test_an_unreachable_robots_is_not_implied_consent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                raise httpx.ConnectError("no route")
            return httpx.Response(200, text=REAL_DESCRIPTION)

        _, result = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert result.ok is False
        assert "robots.txt" in result.reason

    def test_robots_is_fetched_once_per_host(self):
        calls = {"robots": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                calls["robots"] += 1
                return httpx.Response(200, text="")
            return httpx.Response(200, text=REAL_DESCRIPTION)

        c = client_for(handler)
        desc.fetch_description("https://acme.test/jobs/1", client=c)
        desc.fetch_description("https://acme.test/jobs/2", client=c)

        assert calls["robots"] == 1


class TestWhatCountsAsADescription:
    def test_boilerplate_is_reported_as_nothing_readable(self):
        """A login wall or a nav bar is not a short description. Accepting it
        would put junk into match scoring, the tailor and the brief."""
        handler = responder(page="<html><body><nav>Home Jobs Login</nav></body></html>")
        text, result = desc.fetch_description(
            "https://acme.test/jobs/1", client=client_for(handler)
        )

        assert text is None
        assert result.ok is False
        assert "nothing readable" in result.reason

    def test_the_bar_is_length_not_presence(self):
        handler = responder(page=f"<p>{'x' * (desc.MIN_USEFUL_CHARS - 50)}</p>")
        _, result = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert result.ok is False

    def test_markup_is_flattened_to_readable_text(self):
        handler = responder()
        text, _ = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert "<p>" not in text
        assert "<li>" not in text
        assert "Strong fundamentals" in text


class TestFailuresAreReportedNotRaised:
    def test_a_closed_posting_says_so(self):
        handler = responder(status=410)
        _, result = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert result.ok is False
        assert "410" in result.reason
        assert "may already be closed" in result.reason

    def test_a_pdf_link_is_not_a_web_page(self):
        handler = responder(content_type="application/pdf")
        _, result = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert result.ok is False
        assert "not a web page" in result.reason

    def test_an_unreachable_host_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="")
            raise httpx.ConnectTimeout("timed out")

        _, result = desc.fetch_description("https://acme.test/jobs/1", client=client_for(handler))

        assert result.ok is False
        assert "Could not reach" in result.reason

    def test_a_posting_with_no_link_is_not_fetched(self):
        _, result = desc.fetch_description("")

        assert result.ok is False
        assert "no link" in result.reason


class TestPersistence:
    """`refresh_posting` is the only part that writes."""

    @pytest.fixture
    def session(self):
        from sqlalchemy.orm import Session

        from lighthouse.core.db import engine

        connection = engine.connect()
        transaction = connection.begin()
        sess = Session(bind=connection)
        try:
            yield sess
        finally:
            sess.close()
            transaction.rollback()
            connection.close()

    def _posting(self, session):
        from uuid import uuid4

        from lighthouse.core.models import Company, Posting

        slug = uuid4().hex[:12]
        company = Company(name=f"Fixture {slug}", canonical_name=f"fixture {slug}")
        session.add(company)
        session.flush()
        posting = Posting(
            company_id=company.id,
            title="Software Engineer Intern",
            normalized_title="software engineer intern",
            url=f"https://acme.test/jobs/{slug}",
            canonical_url=f"https://acme.test/jobs/{slug}",
            description_available=False,
        )
        session.add(posting)
        session.flush()
        return posting

    def test_a_found_description_is_stored_and_flagged(self, session):
        posting = self._posting(session)

        result = desc.refresh_posting(session, posting, client=client_for(responder()))

        assert result.ok is True
        assert posting.description_available is True
        assert "distributed systems" in posting.description

    def test_a_failed_fetch_leaves_the_posting_alone(self, session):
        """Title-only is an honest state. Half a description is not."""
        posting = self._posting(session)

        result = desc.refresh_posting(
            session, posting, client=client_for(responder(page="<nav>Login</nav>"))
        )

        assert result.ok is False
        assert posting.description is None
        assert posting.description_available is False


class TestPageFurniture:
    """Found against the real thing: a Lever `/apply` page flattened to 109,435
    characters, roughly 90% of it the university dropdown. Several thousand
    school names would have gone into match scoring as though the employer had
    asked for them."""

    def test_a_university_dropdown_is_not_a_description(self):
        schools = "".join(f"<option>{n} University</option>" for n in range(2000))
        page = (
            f"<html><body>{REAL_DESCRIPTION}"
            f"<form><select name='school'>{schools}</select></form></body></html>"
        )
        text, result = desc.fetch_description(
            "https://acme.test/jobs/1", client=client_for(responder(page=page))
        )

        assert result.ok is True
        assert "University" not in text
        assert "distributed systems" in text

    def test_an_application_form_is_refused_not_truncated(self):
        """Half a page cut at an arbitrary point is not a description either,
        and it would look like one."""
        page = "<p>" + ("filler text about the role " * 8000) + "</p>"
        text, result = desc.fetch_description(
            "https://acme.test/jobs/1", client=client_for(responder(page=page))
        )

        assert text is None
        assert result.ok is False
        assert "application form" in result.reason
        assert result.chars > desc.MAX_USEFUL_CHARS

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://jobs.lever.co/acme/abc123/apply", "https://jobs.lever.co/acme/abc123"),
            ("https://jobs.lever.co/acme/abc123/apply/", "https://jobs.lever.co/acme/abc123"),
            ("https://jobs.lever.co/acme/abc123", "https://jobs.lever.co/acme/abc123"),
            ("https://acme.test/careers/apply-now", "https://acme.test/careers/apply-now"),
        ],
    )
    def test_the_apply_page_is_the_form_not_the_posting(self, url, expected):
        assert desc.readable_url(url) == expected

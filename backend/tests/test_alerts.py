"""New-posting alerts.

The pipeline's whole argument is that applying in the first days beats applying
well later, and that only pays off if the operator finds out without opening
the app. So this is the piece that makes freshness matter.

Every filter is a reason *not* to send, and the tests are mostly about
restraint, because the two failure modes do not cost the same. A missed alert
costs a scroll through Discover. A noisy one costs the habit of reading alerts
at all, after which every future alert is worthless too.

DB tests run in a transaction rolled back afterwards."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from lighthouse.alerts import delivery, message, selection, service
from lighthouse.core.db import engine
from lighthouse.core.models import Company, IngestRun, Posting, Season

# The clock sits deliberately ahead of every real row. conftest pins the suite
# to the same database that holds the live posting table, and these functions
# query postings globally -- correctly, since postings are shared rather than
# per-operator. Running the window in the future is what keeps 30,000 real rows
# out of the assertions. Properly fixed by pointing tests at a scratch database
# (roadmap M11.1); until then, this is the isolation.
TODAY = date(2027, 1, 15)
NOW = datetime(2027, 1, 15, 12, 0, tzinfo=UTC)
LAST_RUN = NOW - timedelta(hours=12)


@pytest.fixture
def session():
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    try:
        yield sess
    finally:
        sess.close()
        transaction.rollback()
        connection.close()


def candidate(**kw) -> selection.AlertCandidate:
    base = dict(
        posting_id=str(uuid4()),
        title="Software Engineer Intern",
        company_name="Optiver",
        url="https://example.test/jobs/1",
        match_score=62,
        term_label="Summer 2027",
        location="Austin, TX",
        ghost_label="likely_active",
        top_gaps=["kubernetes", "go"],
        is_thin_evidence=False,
    )
    return selection.AlertCandidate(**{**base, **kw})


def make_posting(session, *, first_seen: datetime, description: str | None = None, **kw):
    slug = uuid4().hex[:12]
    company = Company(name=f"Fixture {slug}", canonical_name=f"fixture {slug}")
    session.add(company)
    session.flush()
    posting = Posting(
        company_id=company.id,
        title=kw.get("title", "Software Engineer Intern"),
        normalized_title="software engineer intern",
        url=f"https://example.test/jobs/{slug}",
        canonical_url=f"https://example.test/jobs/{slug}",
        description=description,
        description_available=description is not None,
        season=Season.SUMMER,
        term_year=2027,
        first_seen_at=first_seen,
        last_seen_at=first_seen,
        is_active=True,
    )
    session.add(posting)
    session.flush()
    return posting


class TestTheWindow:
    def test_only_rows_first_seen_after_the_cutoff(self, session):
        make_posting(session, first_seen=LAST_RUN - timedelta(hours=6))
        fresh = make_posting(session, first_seen=NOW - timedelta(minutes=5))

        picked = selection.select_new_postings(
            session, since=LAST_RUN, min_match=0, today=TODAY
        )
        ids = {c.posting_id for c in picked}

        assert str(fresh.id) in ids
        assert len(ids) == 1

    def test_first_seen_not_posted_at(self, session):
        """`posted_at` is often missing and often wrong. A row that appeared on
        a feed today is new to the operator whatever date it carries."""
        posting = make_posting(session, first_seen=NOW - timedelta(minutes=5))
        posting.posted_at = NOW - timedelta(days=200)
        session.flush()

        picked = selection.select_new_postings(
            session, since=LAST_RUN, min_match=0, today=TODAY
        )

        assert str(posting.id) in {c.posting_id for c in picked}


class TestTheBars:
    def test_a_weak_match_is_not_worth_interrupting_anyone(self, session):
        make_posting(session, first_seen=NOW)

        picked = selection.select_new_postings(
            session, since=LAST_RUN, min_match=90, today=TODAY
        )

        assert picked == []

    def test_a_stale_looking_posting_is_skipped(self, session):
        """Being new does not make a posting the checklist already doubts worth
        chasing."""
        make_posting(session, first_seen=NOW)

        picked = selection.select_new_postings(
            session,
            since=LAST_RUN,
            min_match=0,
            skip_ghost=("likely_active", "probably_fine", "questionable",
                        "likely_stale", "insufficient_data"),
            today=TODAY,
        )

        assert picked == []

    def test_the_burst_cap_holds(self, session):
        """Forty rows from one feed is one digest, not forty emails, and not a
        digest nobody scrolls to the end of."""
        for _ in range(8):
            make_posting(session, first_seen=NOW)

        picked = selection.select_new_postings(
            session, since=LAST_RUN, min_match=0, limit=3, today=TODAY
        )

        assert len(picked) == 3


class TestDigest:
    def test_one_message_carries_every_posting(self):
        body = message.render([candidate(), candidate(title="Backend Intern")])

        assert body.count("https://example.test/jobs/1") == 2
        assert "2 new postings worth a look" in body

    def test_each_line_carries_the_reason(self):
        body = message.render([candidate()])

        assert "62%" in body
        assert "Summer 2027" in body
        assert "Austin, TX" in body
        assert "kubernetes, go" in body

    def test_a_title_only_score_says_so(self):
        """A score from a title alone is weak evidence, and the operator is
        about to decide whether to spend an hour on it."""
        body = message.render([candidate(is_thin_evidence=True)])

        assert "scored from the title only" in body

    def test_a_doubtful_posting_carries_its_checklist_verdict(self):
        body = message.render([candidate(ghost_label="questionable")])

        assert "questionable" in body

    def test_subject_leads_with_whatever_the_body_leads_with(self):
        """Not max(score). Candidates come in Discover's order, which ranks
        title-only matches below fully-compared ones however high their number,
        so the maximum is routinely a thin-evidence 100 near the bottom. A
        subject promising 100% over a body opening at 48% is the small lie that
        stops alerts being read at all."""
        ordered = [
            candidate(match_score=48, is_thin_evidence=False),
            candidate(match_score=100, is_thin_evidence=True),
        ]

        subject = message.subject(ordered)

        assert "48%" in subject
        assert "100%" not in subject
        assert "2 new postings" in subject


class TestDelivery:
    def test_a_failed_send_is_reported_not_raised(self):
        """An alert is a convenience riding on the freshness pipeline. It must
        never be able to fail the ingest run that produced it."""

        class Broken:
            def send(self, message):
                raise AssertionError("should not be called")

        transport = delivery.SmtpTransport(host="127.0.0.1", port=1, use_tls=False, timeout=0.2)
        result = transport.send(
            delivery.build_message(to="a@b.test", sender="c@d.test", subject="s", body="b")
        )

        assert result.sent is False
        assert "Could not send" in result.reason

    def test_capture_transport_records_instead_of_sending(self):
        transport = delivery.CaptureTransport()
        transport.send(
            delivery.build_message(to="a@b.test", sender="c@d.test", subject="s", body="b")
        )

        assert len(transport.messages) == 1
        assert transport.messages[0]["Subject"] == "s"


class TestRunAlert:
    def _settings(self, **kw):
        from types import SimpleNamespace

        base = dict(
            alert_min_match=0,
            alert_skip_ghost=(),
            alert_max_items=25,
            alert_email_to="me@example.test",
            alert_email_from="lighthouse@example.test",
            alerts_configured=True,
        )
        return SimpleNamespace(**{**base, **kw})

    def test_the_first_ever_run_alerts_on_nothing(self, session):
        """No previous run means no window. Alerting on 23,000 rows the first
        time would be the last time anyone read one."""
        run = service.run_alert(session, since=None, settings=self._settings())

        assert run.count == 0
        assert "no 'new' yet" in run.delivered.reason

    def test_nothing_new_sends_no_message(self, session):
        transport = delivery.CaptureTransport()

        run = service.run_alert(
            session,
            since=NOW + timedelta(days=1),
            transport=transport,
            settings=self._settings(),
            today=TODAY,
        )

        assert run.count == 0
        assert transport.messages == []
        assert "no message sent" in run.delivered.reason

    def test_a_hit_is_delivered_once(self, session):
        make_posting(session, first_seen=NOW)
        transport = delivery.CaptureTransport()

        run = service.run_alert(
            session,
            since=LAST_RUN,
            transport=transport,
            settings=self._settings(),
            today=TODAY,
        )

        assert run.count >= 1
        assert len(transport.messages) == 1
        assert transport.messages[0]["To"] == "me@example.test"

    def test_unconfigured_alerts_say_how_to_configure_them(self, session):
        make_posting(session, first_seen=NOW)

        run = service.run_alert(
            session,
            since=LAST_RUN,
            settings=self._settings(alerts_configured=False, alert_email_to="", smtp_host=""),
            today=TODAY,
        )

        assert run.count >= 1
        assert run.delivered.sent is False
        assert "LIGHTHOUSE_ALERT_EMAIL_TO" in run.delivered.reason


class TestCutoff:
    def test_the_cutoff_is_the_previous_run(self, session):
        older = IngestRun(started_at=NOW - timedelta(days=1), max_tier=2)
        newer = IngestRun(started_at=NOW - timedelta(hours=6), max_tier=2)
        session.add_all([older, newer])
        session.flush()

        assert service.previous_run_start(session, before=NOW) == newer.started_at

    def test_no_runs_means_no_cutoff(self, session):
        assert service.previous_run_start(session, before=NOW - timedelta(days=3650)) is None


class TestSmtpForReal:
    """The success path spoken over a socket.

    Everything else here uses the capture transport, which proves the digest is
    right but never proves Lighthouse can speak SMTP. This runs a minimal
    server in-process so the one path the operator will actually depend on is
    exercised rather than mocked."""

    def test_a_message_arrives_intact(self):
        import socket
        import threading

        received: dict[str, bytes] = {}

        def serve(sock):
            conn, _ = sock.accept()
            with conn:
                conn.sendall(b"220 localhost ESMTP\r\n")
                data = b""
                in_body = False
                while True:
                    line = b""
                    while not line.endswith(b"\r\n"):
                        chunk = conn.recv(1)
                        if not chunk:
                            received["body"] = data
                            return
                        line += chunk

                    if in_body:
                        if line == b".\r\n":
                            conn.sendall(b"250 OK\r\n")
                            in_body = False
                            received["body"] = data
                            continue
                        data += line
                        continue

                    upper = line.upper()
                    if upper.startswith(b"EHLO") or upper.startswith(b"HELO"):
                        conn.sendall(b"250-localhost\r\n250 HELP\r\n")
                    elif upper.startswith(b"DATA"):
                        conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                        in_body = True
                    elif upper.startswith(b"QUIT"):
                        conn.sendall(b"221 Bye\r\n")
                        return
                    else:
                        conn.sendall(b"250 OK\r\n")

        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        thread = threading.Thread(target=serve, args=(sock,), daemon=True)
        thread.start()

        try:
            transport = delivery.SmtpTransport(
                host="127.0.0.1", port=port, use_tls=False, timeout=5.0
            )
            result = transport.send(
                delivery.build_message(
                    to="me@example.test",
                    sender="lighthouse@example.test",
                    subject="Lighthouse: 2 new postings, best 48% match",
                    body="  48%  Software Engineer Intern - Optiver\n",
                )
            )
        finally:
            thread.join(timeout=5)
            sock.close()

        assert result.sent is True
        assert result.reason == "Sent."
        body = received.get("body", b"").decode()
        assert "Subject: Lighthouse: 2 new postings, best 48% match" in body
        assert "To: me@example.test" in body
        assert "Software Engineer Intern - Optiver" in body

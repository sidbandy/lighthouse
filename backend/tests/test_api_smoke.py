"""Every endpoint, called the way the browser calls it.

These exist because of a specific bug that every other test missed. A route
handler called another route handler directly to reuse its response; done that
way, FastAPI's ``Query(default=6)`` arrives as the raw ``Query`` object rather
than as ``6``, and the first comparison against it raises. Unit tests over the
service layer all passed, the type checker was happy, and the endpoint returned
500 the moment a browser touched it — surfacing as a CORS error, which points at
entirely the wrong thing.

So: one request per endpoint, asserting it answers at all. Cheap, fast, and it
catches the whole family of "wired up wrong" that pure-function tests cannot
see. Every write goes to a scratch user so the real operator's data is untouched.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from lighthouse.api import app
from lighthouse.core.config import get_settings


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def scratch_operator(monkeypatch):
    """Point writes at an operator that does not exist outside this module."""
    settings = get_settings()
    monkeypatch.setattr(settings, "operator_id", uuid.uuid4(), raising=False)
    yield


class TestReads:
    """Every GET answers. A 500 here is a wiring fault, not a data problem."""

    @pytest.mark.parametrize(
        "path",
        [
            "/health",
            "/api/postings?limit=1",
            "/api/discover?per_lane=1",
            "/api/cycles",
            "/api/sources/health",
            "/api/sources/breakdown",
            "/api/ingest/sources",
            "/api/ingest/refresh",
            "/api/corpus",
            "/api/corpus/stories",
            "/api/corpus/coverage",
            "/api/onboarding",
            "/api/onboarding/majors",
            "/api/applications",
            "/api/resume/versions",
            "/api/network/contacts",
            "/api/network/overview",
            "/api/network/referrals",
            "/api/study",
            "/api/study/patterns",
            "/api/practice/question",
        ],
    )
    def test_it_answers(self, client, path):
        response = client.get(path)
        detail = f"{path} -> {response.status_code} {response.text[:200]}"
        assert response.status_code == 200, detail


class TestWrites:
    def test_logging_an_attempt_returns_the_rebuilt_page(self, client):
        """The exact path that was broken: a POST whose response is the whole
        page, rebuilt."""
        response = client.post(
            "/api/study/attempts",
            json={"problem_slug": "two-sum", "outcome": "solved_clean"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert "suggestions" in body and "patterns" in body and "reviews" in body

    def test_an_unknown_outcome_is_rejected_cleanly(self, client):
        response = client.post(
            "/api/study/attempts",
            json={"problem_slug": "two-sum", "outcome": "nailed_it"},
        )
        assert response.status_code == 422

    def test_reviewing_an_answer_returns_all_three_layers(self, client):
        response = client.post(
            "/api/practice/answer",
            json={
                "transcript": (
                    "We were behind on the pipeline and I had to fix it before the demo. "
                    "So I rewrote the parser. As a result it ran faster."
                ),
                "duration_sec": 60,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["delivery"]["is_measurable"]
        assert len(body["structure"]) == 4
        assert "drift" in body

    def test_an_empty_transcript_is_refused(self, client):
        response = client.post(
            "/api/practice/answer", json={"transcript": "   ", "duration_sec": 10}
        )
        assert response.status_code == 422

    def test_parsing_a_paste_saves_nothing(self, client):
        response = client.post(
            "/api/network/parse",
            json={"text": "Jane Doe\nSoftware Engineer at Stripe"},
        )
        assert response.status_code == 200
        assert [c["name"] for c in response.json()] == ["Jane Doe"]
        assert client.get("/api/network/contacts").json() == []

    def test_a_contact_round_trips(self, client):
        created = client.post(
            "/api/network/contacts",
            json={"name": "Fixture Person", "company_name": "Fixture Co"},
        )
        assert created.status_code == 201, created.text
        contact_id = created.json()["id"]

        logged = client.post(
            f"/api/network/contacts/{contact_id}/interactions",
            json={"kind": "outreach", "summary": "hello"},
        )
        assert logged.status_code == 201
        assert logged.json()["stage"] == "awaiting_reply"

        assert client.delete(f"/api/network/contacts/{contact_id}").status_code == 204

    def test_drafting_refuses_without_a_corpus(self, client):
        """A message about the operator with nothing real behind it is the one
        artifact this project will not produce."""
        created = client.post("/api/network/contacts", json={"name": "Fixture Person"})
        contact_id = created.json()["id"]
        try:
            response = client.post(f"/api/network/contacts/{contact_id}/drafts")
            assert response.status_code == 422
            assert "corpus" in response.json()["detail"].lower()
        finally:
            client.delete(f"/api/network/contacts/{contact_id}")


class TestNotFound:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/postings/00000000-0000-4000-8000-000000000999",
            "/api/network/contacts/00000000-0000-4000-8000-000000000999/drafts",
            "/api/study/patterns/not-a-pattern/problems",
            "/api/study/topics/not-a-topic",
        ],
    )
    def test_unknown_ids_are_404_not_500(self, client, path):
        response = client.post(path) if "drafts" in path else client.get(path)
        assert response.status_code == 404, f"{path} -> {response.status_code}"

"""The source catalogue.

Every feed Lighthouse knows about, declared in one place. Adding a curated list
repo is a single entry here rather than a new module, which is what keeps
breadth cheap as these community repos come and go.

Each source was verified live before being added. They are grouped by tier:

* **1** structured JSON -- richest fields, no parsing risk.
* **2** curated markdown repos -- fastest-moving human curation, incl. off-cycle.
* **3** direct ATS APIs -- freshest, and the only tier carrying descriptions.
* **4** broad aggregators -- boards the curated repos do not cover.
* **5** optional keyed feeds -- off by default.

Sources can be disabled without deleting them, so a repo that goes quiet for a
season can be parked rather than lost.
"""

from __future__ import annotations

from .base import Connector
from .connectors.markdown_repo import MarkdownRepoConnector
from .connectors.simplify import simplify_internships, simplify_new_grad


def _markdown_sources() -> list[Connector]:
    """Tier 2 curated repos.

    ``branch`` matters: several of these default to ``dev`` rather than
    ``main``, and pointing at the wrong one yields a 404 rather than an obvious
    error.
    """
    specs = [
        # (source_id, repo, branch, path, employment_hint, description)
        (
            "vansh_2027",
            "vanshb03/Summer2027-Internships",
            "dev",
            "README.md",
            "internship",
            "vansh / CSCareers 2027 internships",
        ),
        (
            "vansh_offseason",
            "vanshb03/Summer2027-Internships",
            "dev",
            "OFFSEASON_README.md",
            "internship",
            "vansh off-season (Fall/Winter/Spring) internships",
        ),
        (
            "vansh_new_grad",
            "vanshb03/New-Grad-2027",
            "dev",
            "README.md",
            "new_grad",
            "vansh 2027 new-grad roles",
        ),
        (
            "speedyapply_swe",
            "speedyapply/2027-SWE-College-Jobs",
            "main",
            "README.md",
            "internship",
            "speedyapply SWE internships (daily bot)",
        ),
        (
            "speedyapply_swe_new_grad",
            "speedyapply/2027-SWE-College-Jobs",
            "main",
            "NEW_GRAD_USA.md",
            "new_grad",
            "speedyapply SWE new-grad USA",
        ),
        (
            "speedyapply_ai",
            "speedyapply/2027-AI-College-Jobs",
            "main",
            "README.md",
            "internship",
            "speedyapply AI/ML internships",
        ),
        (
            "sndsh_offseason",
            "sndsh404/summer-2027-internships",
            "main",
            "README.md",
            "internship",
            "sndsh Summer 2027 + off-season",
        ),
        (
            "zapply_internships",
            "zapplyjobs/Internships-2027",
            "main",
            "README.md",
            "internship",
            "zapplyjobs 2027 internships",
        ),
        (
            "zapply_new_grad_swe",
            "zapplyjobs/New-Grad-Software-Engineering-Jobs-2027",
            "main",
            "README.md",
            "new_grad",
            "zapplyjobs new-grad SWE",
        ),
        # NOTE: zapplyjobs/underclassmen-internships is deliberately absent.
        # Its table is a programme directory (name / open date / year / note),
        # not job postings, so it belongs to the Companies module rather than
        # here. The connector's column check correctly refuses to parse it.
        (
            "jobright_swe_intern",
            "jobright-ai/2026-Software-Engineer-Internship",
            "master",
            "README.md",
            "internship",
            "jobright SWE internships",
        ),
        (
            "jobright_swe_new_grad",
            "jobright-ai/2026-Software-Engineer-New-Grad",
            "master",
            "README.md",
            "new_grad",
            "jobright SWE new-grad",
        ),
    ]
    return [
        MarkdownRepoConnector(
            source_id=source_id,
            repo=repo,
            branch=branch,
            path=path,
            employment_hint=hint,
            description=description,
        )
        for source_id, repo, branch, path, hint, description in specs
    ]


def all_connectors() -> list[Connector]:
    """Every registered source, tier order."""
    return [simplify_internships(), simplify_new_grad(), *_markdown_sources()]


def connectors_by_tier(max_tier: int = 5) -> list[Connector]:
    """Sources up to and including ``max_tier``.

    Useful for a fast refresh: tiers 1-2 alone give a complete, usable list in
    seconds, with the slower breadth tiers layered on when wanted.
    """
    return [c for c in all_connectors() if c.tier <= max_tier]


def get_connector(source_id: str) -> Connector | None:
    return next((c for c in all_connectors() if c.source_id == source_id), None)

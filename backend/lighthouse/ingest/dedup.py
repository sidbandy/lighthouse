"""Collapsing the same real-world role seen across many feeds.

With 15+ overlapping sources the same Optiver posting arrives three times with
different text, different location formatting and different tracking
parameters. Without dedup the list is unusable; with naive dedup it is wrong in
both directions -- over-merging two genuinely different roles at one company,
and under-merging rows that differ only by whitespace.

The strategy, cheapest and most certain signal first:

1. **Block** by canonical company, so we never compare across companies. This
   also keeps the work linear rather than quadratic over the whole corpus.
2. **Job-ID veto.** Two rows whose ATS job ids differ are different roles, full
   stop. This is checked *before* anything fuzzy and overrides everything --
   it is the guard that stops "Software Engineer Intern" at one company
   collapsing into a single row.
3. **Canonical URL** equality. Same URL, same posting. Catches most duplicates
   outright.
4. **Fuzzy title** match above a high threshold, for rows that describe the
   same role but link to different mirrors of it.

On merge we keep the earliest posting date, the longest description, the union
of locations, and every source id -- so the UI can say "seen on 4 lists" and
the operator can see where each came from.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .base import RawPosting

# Token-set ratio at or above this counts as the same role. Set high on
# purpose: a false merge silently hides a real job, which is worse than showing
# a near-duplicate the operator can dismiss.
TITLE_MATCH_THRESHOLD = 90


@dataclass
class MergedPosting:
    """A canonical posting plus every raw sighting that produced it."""

    primary: RawPosting
    members: list[RawPosting] = field(default_factory=list)

    @property
    def source_ids(self) -> list[str]:
        return sorted({m.source_id for m in self.members})

    @property
    def source_count(self) -> int:
        return len(self.source_ids)

    @property
    def company_name(self) -> str:
        """Prefer the longest spelling: "Jump Trading Group" over "Jump"."""
        return max((m.company_name for m in self.members), key=len)

    @property
    def title(self) -> str:
        return max((m.title for m in self.members), key=len)

    @property
    def description(self) -> str | None:
        """Longest available description. Many feeds carry none at all."""
        described = [m.description for m in self.members if m.has_description]
        return max(described, key=len) if described else None

    @property
    def url(self) -> str:
        return self.primary.url

    @property
    def canonical_url(self) -> str:
        return self.primary.canonical_url_value

    @property
    def ats_job_id(self) -> str | None:
        for member in self.members:
            if member.ats_job_id:
                return member.ats_job_id
        return None

    @property
    def ats_vendor(self) -> str | None:
        for member in self.members:
            if member.ats_vendor:
                return member.ats_vendor
        return None

    @property
    def posted_at(self):
        """Earliest sighting. A later feed re-listing an old role does not make
        it new, and posting age drives the ghost-job signals."""
        dates = [m.posted_at for m in self.members if m.posted_at]
        return min(dates) if dates else None

    @property
    def updated_at(self):
        dates = [m.updated_at for m in self.members if m.updated_at]
        return max(dates) if dates else None

    @property
    def is_active(self) -> bool:
        """Active if any source still lists it as open. Feeds mark roles closed
        at different times, so the optimistic read avoids hiding live roles."""
        return any(m.is_active for m in self.members)

    @property
    def locations(self) -> list[dict]:
        """Union across sources.

        One feed saying "Chicago, IL" and another "4 locations: Chicago, NYC,
        Miami, Houston" are the same posting -- the second simply has better
        data, so we take the superset.
        """
        merged: dict[str, dict] = {}
        for member in self.members:
            for loc in member.locations:
                # Key on the city alone so a bare "Chicago" and a fully
                # qualified "Chicago, IL" reconcile into one entry rather than
                # listing the same office twice.
                city = (loc.get("city") or "").strip().lower()
                key = city or f"remote|{loc.get('is_remote')}" or (loc.get("raw") or "").lower()

                current = merged.get(key)
                if current is None:
                    merged[key] = dict(loc)
                    continue
                # Keep whichever entry knows more: a state beats no state.
                if loc.get("state") and not current.get("state"):
                    merged[key] = dict(loc)
                elif loc.get("is_remote"):
                    current["is_remote"] = True
        return list(merged.values())

    @property
    def location_labels(self) -> list[str]:
        from .normalize import location_label

        return sorted({label for loc in self.locations if (label := location_label(loc))})

    @property
    def is_remote(self) -> bool:
        return any(loc.get("is_remote") for loc in self.locations)

    @property
    def explicit_terms(self) -> list[str]:
        return sorted({t for m in self.members for t in m.explicit_terms})

    @property
    def sponsorship_raw(self) -> str | None:
        """Any source flagging a restriction wins; a missed restriction wastes
        an application, a spurious one only costs a second look."""
        for member in self.members:
            if member.sponsorship_raw:
                return member.sponsorship_raw
        return None

    @property
    def employment_hint(self) -> str | None:
        for member in self.members:
            if member.employment_hint:
                return member.employment_hint
        return None


def _same_posting(a: RawPosting, b: RawPosting) -> bool:
    """Whether two rows in the same company block are the same role."""
    # Rule 2: job-id disagreement is an absolute veto, checked first.
    if a.ats_job_id and b.ats_job_id:
        return a.ats_job_id == b.ats_job_id

    # Rule 3: identical canonical URL.
    if a.canonical_url_value and a.canonical_url_value == b.canonical_url_value:
        return True

    # Rule 4: near-identical titles. Only one side having a job id is not
    # evidence either way, so titles decide.
    if not a.normalized_title_value or not b.normalized_title_value:
        return False
    return (
        fuzz.token_set_ratio(a.normalized_title_value, b.normalized_title_value)
        >= TITLE_MATCH_THRESHOLD
    )


def deduplicate(postings: list[RawPosting]) -> list[MergedPosting]:
    """Collapse raw postings into canonical ones.

    Ordering is made deterministic before grouping so that repeated runs over
    the same input produce identical output, which keeps the run-to-run diff
    used for new-posting alerts meaningful.
    """
    blocks: dict[str, list[RawPosting]] = defaultdict(list)
    for posting in postings:
        if posting.is_valid():
            blocks[posting.canonical_company_name].append(posting)

    merged: list[MergedPosting] = []
    for _, block in sorted(blocks.items()):
        # Rows with a job id first, then longest title: the richest row becomes
        # the primary and weaker rows attach to it.
        block.sort(key=lambda p: (p.ats_job_id is None, -len(p.title), p.canonical_url_value))
        groups: list[MergedPosting] = []
        for posting in block:
            for group in groups:
                if _same_posting(group.primary, posting):
                    group.members.append(posting)
                    break
            else:
                groups.append(MergedPosting(primary=posting, members=[posting]))
        merged.extend(groups)
    return _fold_shared_urls(merged)


def _fold_shared_urls(merged: list[MergedPosting]) -> list[MergedPosting]:
    """Rule 3, applied across company blocks as well as within them.

    Blocking by company is what keeps dedup linear, but it means two spellings
    of one employer are never compared. Akuna lists the same job as "Akuna
    Capital" on some feeds and "Akuna Capital University" on others, so one
    role -- one URL, one ``gh_jid`` -- became two postings, two cards in a
    lane, and two rows racing for a column the database says is unique.
    Measured live before this existed: 59 URLs claimed twice in a single run.

    Only the URL crosses the block. A canonical URL *is* the posting's
    identity, which is exactly what the unique index on ``postings.canonical_url``
    asserts, so this adds no judgement -- nothing fuzzy, no title comparison,
    no company-name guessing. Two rows that merely look alike at differently
    spelled companies still stay apart.

    The first group to claim a URL keeps its primary. Blocks are walked in
    sorted company order, so which one that is stays stable run to run, which
    the new-posting diff depends on.
    """
    by_url: dict[str, MergedPosting] = {}
    folded: list[MergedPosting] = []
    for group in merged:
        url = group.canonical_url
        if not url:
            folded.append(group)
            continue
        winner = by_url.get(url)
        if winner is None:
            by_url[url] = group
            folded.append(group)
        else:
            winner.members.extend(group.members)
    return folded


def dedup_stats(raw_count: int, merged: list[MergedPosting]) -> dict[str, int]:
    """Summary for the ingest report and the source-health panel."""
    multi = [m for m in merged if m.source_count > 1]
    return {
        "raw": raw_count,
        "merged": len(merged),
        "collapsed": raw_count - len(merged),
        "multi_source": len(multi),
    }

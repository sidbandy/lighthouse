"""New-posting alerts: learning a posting opened without opening the app.

Differentiator #2 is that applying in the first days is worth more than
applying well later, and the whole freshness pipeline exists to serve it. That
argument only pays off if the operator finds out. Twice-daily ingest into a
list nobody has open is a list that gets read the next time someone happens to
look, which is exactly the delay the pipeline was built to remove.

Two rules shape everything here:

* **An alert that fires on everything is an alert nobody reads.** A run adds
  hundreds of rows. The filters exist to get that to the handful worth
  interrupting a day for, and the bar is deliberately high -- the full list is
  still in Discover either way, so a miss costs a scroll and a false alarm
  costs the operator's trust in every future message.
* **A burst is one message.** Forty new rows from one feed is one digest, not
  forty emails.
"""

from .selection import AlertCandidate, select_new_postings
from .service import AlertRun, previous_run_start, run_alert

__all__ = [
    "AlertCandidate",
    "AlertRun",
    "previous_run_start",
    "run_alert",
    "select_new_postings",
]

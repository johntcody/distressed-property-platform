"""Daily digest generator.

build_digest_rows() queries the alerts table for the prior 24 hours,
groups by user (via subscription_id → user), and returns one digest
message per user. The caller (a scheduled Lambda or cron job) is
responsible for actually sending the messages via notifier.dispatch().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID


_DIGEST_WINDOW_HOURS = 24

_FETCH_SQL = """\
SELECT
    a.id,
    a.property_id,
    a.trigger_type,
    a.trigger_score,
    a.channel,
    a.contact,
    a.sent_at,
    sub.user_id
FROM alerts a
JOIN alert_subscriptions sub ON sub.id = a.subscription_id
WHERE a.sent_at >= $1
ORDER BY sub.user_id, a.sent_at DESC
"""


@dataclass
class DigestEntry:
    user_id:  UUID
    channel:  str
    contact:  str
    lines:    list[str]   # one summary line per alert

    @property
    def alert_count(self) -> int:
        return len(self.lines)


async def build_digest_rows(pool) -> list[DigestEntry]:
    """Return one DigestEntry per user that received alerts in the last 24 h."""
    since = datetime.now(tz=timezone.utc) - timedelta(hours=_DIGEST_WINDOW_HOURS)
    rows = await pool.fetch(_FETCH_SQL, since)

    by_user: dict[UUID, DigestEntry] = {}
    for row in rows:
        uid = row["user_id"]
        if uid not in by_user:
            by_user[uid] = DigestEntry(
                user_id=uid,
                channel=row["channel"],
                contact=row["contact"],
                lines=[],
            )
        entry = by_user[uid]
        score_str = f"  score {row['trigger_score']:.0f}" if row["trigger_score"] else ""
        entry.lines.append(
            f"• {row['trigger_type'].replace('_', ' ').title()}"
            f" — property {row['property_id']}{score_str}"
        )

    return list(by_user.values())


def format_digest(entry: DigestEntry) -> tuple[str, str]:
    """Return (subject, body) for one user's digest email/SMS/push."""
    subject = f"Your daily distressed-property digest — {entry.alert_count} alert(s)"
    body = "\n".join(["New alerts in the last 24 hours:", ""] + entry.lines)
    return subject, body

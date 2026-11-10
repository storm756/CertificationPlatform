"""The impact of changing marks or counted parts (architecture §10.4).

The preview calls `compute_results` twice, as it is now and with the proposed change applied in
memory, so it can never disagree with the real results after the change is confirmed.
"""

from apps.accounts.models import Role, User

from .policy import compute_results

LIST_LIMIT = 50


def impact(overrides: dict) -> dict:
    ids = list(User.objects.filter(role=Role.LEARNER).values_list("pk", flat=True))
    before = compute_results(ids)
    after = compute_results(ids, overrides)
    lose = [u for u in ids if before[u].meets_requirements and not after[u].meets_requirements]
    gain = [u for u in ids if after[u].meets_requirements and not before[u].meets_requirements]
    changed = [u for u in ids if before[u].overall_shown != after[u].overall_shown]
    return {
        "learners": len(ids),
        "lose": lose,
        "gain": gain,
        "overall_changed": len(changed),
        "eligible_before": sum(1 for u in ids if before[u].meets_requirements),
        "eligible_after": sum(1 for u in ids if after[u].meets_requirements),
        "gaps_after": next(iter(after.values())).setup_gaps if after else [],
        "list_limit": LIST_LIMIT,
    }

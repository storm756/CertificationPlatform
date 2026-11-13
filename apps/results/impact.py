"""The impact of changing marks or counted parts (architecture §10.4).

The preview calls `compute_results` twice, as it is now and with the proposed change applied in
memory, so it can never disagree with the real results after the change is confirmed. The headline
numbers use the real `eligible` rule (which includes the course set-up checks), so what the preview
says is what the dashboard will say. A second pair of numbers ignores set-up gaps, to show the
effect of the marks alone while the course is still being completed.
"""

import hashlib
import json

from apps.accounts.models import Role, User

from .policy import compute_results

LIST_LIMIT = 50


def impact(overrides: dict) -> dict:
    ids = list(User.objects.filter(role=Role.LEARNER).values_list("pk", flat=True))
    before = compute_results(ids)
    after = compute_results(ids, overrides)
    lose = [u for u in ids if before[u].eligible and not after[u].eligible]
    gain = [u for u in ids if after[u].eligible and not before[u].eligible]
    lose_marks = [
        u for u in ids if before[u].meets_requirements and not after[u].meets_requirements
    ]
    gain_marks = [
        u for u in ids if after[u].meets_requirements and not before[u].meets_requirements
    ]
    changed = [u for u in ids if before[u].overall_shown != after[u].overall_shown]
    gaps_before = next(iter(before.values())).setup_gaps if before else []
    return {
        "learners": len(ids),
        "lose": lose,
        "gain": gain,
        "lose_marks": lose_marks,
        "gain_marks": gain_marks,
        "overall_changed": len(changed),
        "eligible_before": sum(1 for u in ids if before[u].eligible),
        "eligible_after": sum(1 for u in ids if after[u].eligible),
        "gaps_before": gaps_before,
        "gaps_after": next(iter(after.values())).setup_gaps if after else [],
        "list_limit": LIST_LIMIT,
    }


def digest(overrides: dict, result: dict) -> str:
    """A fingerprint of the proposal and the exact learners it would move. The confirm step must
    present the same digest the preview showed, so what is saved is what was previewed."""
    payload = {
        "overrides": {
            "parts": {str(k): v for k, v in sorted(overrides["parts"].items())},
            "modules": {str(k): v for k, v in sorted(overrides["modules"].items())},
        },
        "lose": sorted(result["lose"]),
        "gain": sorted(result["gain"]),
        "after": result["eligible_after"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

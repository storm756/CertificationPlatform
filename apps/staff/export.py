"""The admin's per-batch learner report as CSV (pilot hardening; the HOD's programme brief).

One row per enrolled learner: pre-test %, first and best final %, knowledge gain, modules passed,
hours and the certificate number. The gain is the existing one (apps.results.insights.knowledge_gain):
points gained on the shared pre-test questions between the pre-test and the learner's FIRST final,
the same figure the Report page averages per batch. Hours come from apps.content.services.hours_for:
engaged time for adults, the nominal minutes of finished lessons for under-18s (D16: no tracking).

Every text cell is spreadsheet-safe (apps.mentors.export.safe_cell) and the file starts with a BOM.
"""

import csv
import io
from decimal import Decimal

from apps.assessments.models import Attempt, ProgrammeAssessmentKind
from apps.batches.models import Enrolment
from apps.certificates.models import Certificate, CertificateStatus
from apps.content.services import hours_for
from apps.mentors.export import BOM, safe_cell
from apps.results import insights
from apps.results.policy import compute_results, round1

SUBMITTED = ("submitted", "auto_submitted")
HEADER = [
    "Batch",
    "Name",
    "Email",
    "Pre-test %",
    "First final %",
    "Best final %",
    "Gain (pts)",
    "Modules passed",
    "Hours",
    "Hours basis",
    "Certificate number",
]


def _programme_scores(user_ids) -> tuple[dict, dict]:
    """({user: pre-test %}, {user: first final %}) from submitted attempts, as stored (one decimal)."""
    pretest, first_final = {}, {}
    rows = (
        Attempt.objects.filter(
            user_id__in=user_ids,
            status__in=SUBMITTED,
            programme_assessment__kind__in=[
                ProgrammeAssessmentKind.PRETEST,
                ProgrammeAssessmentKind.FINAL,
            ],
        )
        .order_by("number")
        .values_list("user_id", "programme_assessment__kind", "score")
    )
    for user_id, kind, score in rows:
        target = pretest if kind == ProgrammeAssessmentKind.PRETEST else first_final
        target.setdefault(user_id, score)  # ordered by number: the first one wins
    return pretest, first_final


def _hours(user) -> tuple[Decimal, str]:
    spent = hours_for(user)
    hours = round1(Decimal(spent["minutes"]) / Decimal(60))
    return hours, "engaged" if spent["kind"] == "engaged" else "nominal (under 18)"


def batch_report_rows(batch) -> list[dict]:
    enrolments = list(
        Enrolment.objects.filter(batch=batch)
        .select_related("user", "user__profile")
        .order_by("user__profile__certificate_name", "user_id")
    )
    ids = [e.user_id for e in enrolments]
    results = compute_results(ids)
    pretest, first_final = _programme_scores(ids)
    numbers = dict(
        Certificate.objects.filter(user_id__in=ids, status=CertificateStatus.ISSUED).values_list(
            "user_id", "certificate_no"
        )
    )
    rows = []
    for e in enrolments:
        r = results[e.user_id]
        counted = [m for m in r.modules if m.parts]
        hours, basis = _hours(e.user)
        rows.append(
            {
                "name": e.user.profile.certificate_name,
                "email": e.user.email,
                "pretest": pretest.get(e.user_id),
                "first_final": first_final.get(e.user_id),
                "best_final": r.final_shown if r.final_attempts else None,
                "gain": insights.knowledge_gain(e.user),
                "modules_passed": f"{sum(1 for m in counted if m.passed)}/{len(r.modules)}",
                "hours": hours,
                "hours_basis": basis,
                "certificate": numbers.get(e.user_id, ""),
            }
        )
    return rows


def _text(value) -> str:
    return "" if value is None else str(value)


def batch_report_csv(batch, rows=None) -> str:
    rows = batch_report_rows(batch) if rows is None else rows
    out = io.StringIO()
    out.write(BOM)
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow([safe_cell(h) for h in HEADER])
    for row in rows:
        line = [
            batch.code,
            row["name"],
            row["email"],
            _text(row["pretest"]),
            _text(row["first_final"]),
            _text(row["best_final"]),
            _text(row["gain"]),
            row["modules_passed"],
            _text(row["hours"]),
            row["hours_basis"],
            row["certificate"],
        ]
        writer.writerow([safe_cell(x) for x in line])
    return out.getvalue()

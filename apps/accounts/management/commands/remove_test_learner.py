"""Remove one test learner (and what hangs off the account), for pilot testing on prod.

    manage.py remove_test_learner me+test1@gmail.com            # shows what it would delete
    manage.py remove_test_learner me+test1@gmail.com --yes      # deletes
    manage.py remove_test_learner ... --yes --include-certificate

Only learners: a mentor or an admin is refused. The admin cannot delete a user who holds a
certificate (Certificate.user is PROTECT), so a learner with a certificate is refused too unless
--include-certificate is given. Deleting a certificate leaves a gap in the serial numbers (one
global sequence, never reused), and the command says so before it deletes.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError

from apps.accounts.models import Role, User
from apps.audit.services import audit
from apps.certificates.models import Certificate
from apps.certificates.services import pdf_file


class Command(BaseCommand):
    help = "Delete one test learner account. Learners only; needs --yes."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--yes", action="store_true", help="Really delete (default: preview).")
        parser.add_argument(
            "--include-certificate",
            action="store_true",
            help="Also delete the learner's certificate(s). Leaves a gap in the serial numbers.",
        )

    def handle(self, *args, email, yes, include_certificate, **options):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"No account with the address {email}.")
        if user.role != Role.LEARNER:
            raise CommandError(
                f"{email} is a {user.role}, not a learner. This command only removes learners."
            )
        certificates = list(Certificate.objects.filter(user=user))
        attempts = user.attempts.count() if hasattr(user, "attempts") else 0
        self.stdout.write(f"Learner {user.email} (id {user.pk}) will be deleted with:")
        self.stdout.write(f"  - {attempts} attempt(s) and their answers")
        self.stdout.write("  - their profile, batch enrolment and sign-in sessions")
        for cert in certificates:
            self.stdout.write(f"  - certificate {cert.certificate_no}")
        if certificates and not include_certificate:
            raise CommandError(
                "This learner holds a certificate, so the account is kept. Run again with "
                "--include-certificate if you really want it gone."
            )
        if certificates:
            self.stdout.write(
                self.style.WARNING(
                    "Deleting a certificate leaves a gap in the serial numbers: they come from "
                    "one global sequence and are never reused or renumbered."
                )
            )
        if not yes:
            self.stdout.write("Nothing deleted. Add --yes to delete.")
            return
        files = [path for c in certificates if (path := pdf_file(c)) is not None]
        user_id = user.pk
        try:
            with transaction.atomic():
                for cert in certificates:
                    cert.delete()
                user.delete()
                audit(
                    "user.test_learner_removed",
                    user_id=user_id,
                    certificates=len(certificates),
                )
        except ProtectedError as exc:
            raise CommandError(f"Something still depends on this account: {exc}") from exc
        stuck = []
        for path in files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                stuck.append(path)
        self.stdout.write(self.style.SUCCESS("Deleted."))
        if stuck:
            listing = "\n".join(f"  {p}" for p in stuck)
            self.stdout.write(
                self.style.WARNING(
                    "The account is gone but these certificate PDFs could not be removed:\n"
                    f"{listing}\n"
                    "Delete them by hand with a one-off root container on the media volume "
                    "(docs/runbook.md 10.3). They are private files holding only that test "
                    "learner's details."
                )
            )

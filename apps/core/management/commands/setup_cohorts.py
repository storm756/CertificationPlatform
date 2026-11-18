"""Initialize realistic student cohorts across multiple batches.

Creates 693 learners distributed across 5 batches (CCFR-B02 to CCFR-B06) spanning
November 2026 to January 2027. Includes deep behavioural history: spread-out registration dates,
calendar-spaced UnitProgress, realistic TimeLogs, multi-attempt exams (fail then retry),
and question-level AttemptItem entries.

Usage:
    python manage.py setup_cohorts --preview        # Dry-run preview
    python manage.py setup_cohorts                  # Initialize 693 learners
    python manage.py setup_cohorts --clean-cohorts  # Remove the cohorts' accounts and batches

--clean-cohorts removes the batches, accounts, enrolments, attempts and activity this command
created. It does NOT remove the units, live questions and assessment parts that setup adds to the
course, so it does not restore the curriculum to its earlier state.
"""

import json
import random
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile, Role, User, UserStatus
from apps.assessments import programme
from apps.assessments.models import (
    AssessmentPart,
    Attempt,
    AttemptItem,
    AttemptStatus,
    PartFamily,
    ProgrammeAssessmentKind,
    Selection,
)
from apps.assessments.rules import publish_part
from apps.batches.models import Batch, Enrolment
from apps.content.models import Module, ModuleKind, TimeLog, Unit, UnitProgress
from apps.questions import formats
from apps.questions import services as qservices
from apps.questions.models import Pool, Question, QuestionStatus
from apps.results.policy import percent

MANIFEST_PATH = Path(settings.BASE_DIR) / "data" / "cohort_693_manifest.json"
DATA_FILE_PATH = Path(settings.BASE_DIR) / "data" / "learners_693_clean.json"
DEFAULT_CENTRE_CODE = "SAKEC"
# Synthetic learners never get a deliverable address (a real person could own it).
SYNTHETIC_EMAIL_DOMAIN = "cohort.example.com"


def allocate(total_count):
    """Seats per batch: each share rounded down, then the remainder handed to the largest
    fractional parts, so the shares always add up to exactly total_count."""
    weights = [b["target_count"] for b in BATCH_CONFIG]
    weight_sum = sum(weights)
    base = [total_count * w // weight_sum for w in weights]
    order = sorted(
        range(len(weights)),
        key=lambda i: (-((total_count * weights[i]) % weight_sum), i),
    )
    for i in order[: total_count - sum(base)]:
        base[i] += 1
    return {b["code"]: n for b, n in zip(BATCH_CONFIG, base, strict=True)}


BATCH_CONFIG = [
    {
        "code": "CCFR-B02",
        "name": "CCFR Batch_02",
        "start_date": date(2026, 9, 20),
        "end_date": date(2026, 10, 18),
        "opens_at": datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        "closes_at": datetime(2026, 10, 5, 23, 59, tzinfo=UTC),
        "accepting": False,
        "target_count": 148,
        "stage": "senior_complete",
    },
    {
        "code": "CCFR-B03",
        "name": "CCFR Batch_03",
        "start_date": date(2026, 10, 10),
        "end_date": date(2026, 11, 5),
        "opens_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        "closes_at": datetime(2026, 10, 22, 23, 59, tzinfo=UTC),
        "accepting": False,
        "target_count": 136,
        "stage": "mature_complete",
    },
    {
        "code": "CCFR-B04",
        "name": "CCFR Batch_04",
        "start_date": date(2026, 10, 25),
        "end_date": date(2026, 11, 22),
        "opens_at": datetime(2026, 10, 18, 9, 0, tzinfo=UTC),
        "closes_at": datetime(2026, 11, 10, 23, 59, tzinfo=UTC),
        "accepting": False,
        "target_count": 142,
        "stage": "mid_progress",
    },
    {
        "code": "CCFR-B05",
        "name": "CCFR Batch_05",
        "start_date": date(2026, 11, 5),
        "end_date": date(2026, 12, 2),
        "opens_at": datetime(2026, 10, 28, 9, 0, tzinfo=UTC),
        "closes_at": datetime(2026, 11, 15, 23, 59, tzinfo=UTC),
        "accepting": False,
        "target_count": 135,
        "stage": "early_progress",
    },
    {
        "code": "CCFR-B06",
        "name": "CCFR Batch_06",
        "start_date": date(2026, 11, 12),
        "end_date": date(2026, 12, 10),
        "opens_at": datetime(2026, 11, 5, 9, 0, tzinfo=UTC),
        "closes_at": datetime(2026, 11, 30, 23, 59, tzinfo=UTC),
        "accepting": True,
        "target_count": 132,
        "stage": "fresh_enrolled",
    },
]

FIRST_NAMES = [
    "Aarav",
    "Aditya",
    "Akash",
    "Amit",
    "Ananya",
    "Anjali",
    "Ankush",
    "Arjun",
    "Deepa",
    "Deepak",
    "Divya",
    "Gaurav",
    "Harish",
    "Ishaan",
    "Karan",
    "Kavya",
    "Kritika",
    "Lakshmi",
    "Manish",
    "Meera",
    "Nandini",
    "Nikhil",
    "Nisha",
    "Pallavi",
    "Pavan",
    "Pooja",
    "Preeti",
    "Priya",
    "Rahul",
    "Rajesh",
    "Ramya",
    "Riya",
    "Rohan",
    "Rohit",
    "Sakshi",
    "Sandeep",
    "Sanjay",
    "Shivani",
    "Shweta",
    "Sneha",
    "Suresh",
    "Swati",
    "Tanvi",
    "Tanya",
    "Usha",
    "Varun",
    "Vikram",
    "Vimal",
    "Vishal",
    "Yamini",
    "Yash",
    "Avinash",
    "Bhavna",
    "Chetan",
    "Darshan",
    "Hemant",
]

LAST_NAMES = [
    "Patel",
    "Sharma",
    "Verma",
    "Gupta",
    "Singh",
    "Kumar",
    "Joshi",
    "Reddy",
    "Nair",
    "Rao",
    "Mishra",
    "Pandey",
    "Thakur",
    "Shah",
    "Mehta",
    "Chaudhary",
    "Pillai",
    "Iyer",
    "Krishnan",
    "Bose",
    "Kulkarni",
    "Deshmukh",
    "Chavan",
    "Shinde",
    "Pawar",
    "Gaikwad",
    "More",
    "Bhide",
    "Sawant",
    "Bhat",
    "Rane",
    "Gokhale",
    "Dhar",
    "Banerjee",
    "Chatterjee",
    "Mhatre",
    "Salvi",
    "Tambe",
    "Gore",
    "Jadhav",
]


class Command(BaseCommand):
    help = "Initialize realistic student cohorts across multiple batches."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=693, help="Total learners (default: 693)")
        parser.add_argument(
            "--preview", action="store_true", help="Print simulation overview without writing to DB"
        )
        parser.add_argument(
            "--clean-cohorts", action="store_true", help="Remove all cohorts and their data"
        )

    def handle(self, *args, **options):
        if options["clean_cohorts"] and options["preview"]:
            raise CommandError(
                "--preview cannot be combined with --clean-cohorts (nothing was deleted)."
            )
        if options["count"] <= 0:
            raise CommandError("--count must be a positive number.")

        if options["clean_cohorts"]:
            self._clean_cohorts()
            return

        if options["preview"]:
            self._preview(options["count"])
            return

        self._populate(options["count"])

    def _preview(self, total_count):
        self.stdout.write(self.style.MIGRATE_HEADING("=== CCFR Cohort Simulation Preview ==="))
        self.stdout.write(f"Total Target Learners: {total_count}")
        self.stdout.write(f"Identity Source: {DATA_FILE_PATH.name} (693 unique Indian identities)")
        self.stdout.write(f"Batches: {len(BATCH_CONFIG)} cohorts (Nov 2026 - Jan 2027)\n")

        total_allocated = 0
        shares = allocate(total_count)
        for b in BATCH_CONFIG:
            count = shares[b["code"]]
            total_allocated += count
            self.stdout.write(
                f"  [{b['code']}] {b['name']:<16} | Status: {'OPEN' if b['accepting'] else 'CLOSED':<6} | "
                f"Learners: {count:<4} | Stage: {b['stage']}"
            )
        self.stdout.write(f"\nNet Allocated: {total_allocated} learners")
        self.stdout.write("Run without --preview to execute database initialization.")

    def _clean_cohorts(self):
        batch_codes = [b["code"] for b in BATCH_CONFIG]
        self.stdout.write(f"Cleaning cohorts: {', '.join(batch_codes)}...")

        with transaction.atomic():
            batches = Batch.objects.filter(code__in=batch_codes)
            enrolments = Enrolment.objects.filter(batch__in=batches)
            user_ids = list(enrolments.values_list("user_id", flat=True))

            # Also check manifest if present
            if MANIFEST_PATH.exists():
                try:
                    with open(MANIFEST_PATH, encoding="utf-8") as f:
                        data = json.load(f)
                    manifest_ids = [item["id"] for item in data.get("learners", []) if "id" in item]
                    user_ids = list(set(user_ids + manifest_ids))
                except (json.JSONDecodeError, OSError):
                    pass

            n_time = TimeLog.objects.filter(user_id__in=user_ids).delete()[0]
            n_prog = UnitProgress.objects.filter(user_id__in=user_ids).delete()[0]
            n_items = AttemptItem.objects.filter(attempt__user_id__in=user_ids).delete()[0]
            n_attempts = Attempt.objects.filter(user_id__in=user_ids).delete()[0]
            n_enrol = enrolments.delete()[0]
            n_users = User.objects.filter(id__in=user_ids).delete()[0]
            n_batches = batches.delete()[0]

            # Remove the manifest only once this transaction has really committed.
            transaction.on_commit(lambda: MANIFEST_PATH.unlink(missing_ok=True))

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup complete: {n_batches} batches, {n_users} users, {n_enrol} enrolments, "
                f"{n_attempts} attempts, {n_items} attempt items, {n_prog} progress, {n_time} time logs."
            )
        )

    def _populate(self, total_count):
        rng = random.Random(20261117)
        self.stdout.write(f"Preparing {total_count} learners across 5 cohorts...")

        shares = allocate(total_count)

        # Validate the whole roster before anything is written.
        learners_source = self._load_roster()

        # 1. Ensure batches exist
        db_batches = {}
        for b_conf in BATCH_CONFIG:
            batch, _ = Batch.objects.get_or_create(
                code=b_conf["code"],
                defaults={
                    "name": b_conf["name"],
                    "accepting": b_conf["accepting"],
                    "opens_at": b_conf["opens_at"],
                    "closes_at": b_conf["closes_at"],
                    "start_date": b_conf["start_date"],
                    "end_date": b_conf["end_date"],
                    "seat_limit": b_conf["target_count"] + 30,
                    "centre": "",
                    "centre_code": DEFAULT_CENTRE_CODE,
                },
            )
            db_batches[b_conf["code"]] = (batch, b_conf)

        # 2. Ensure course content exists (units, questions, assessment parts)
        self._ensure_course_content()

        # 3. Gather learning units and assessment parts
        learning_modules = list(
            Module.objects.filter(kind=ModuleKind.LEARNING, counted=True).order_by("number")
        )
        all_units = list(
            Unit.objects.filter(module__in=learning_modules).order_by("module__number", "order")
        )
        counted_parts = list(
            AssessmentPart.objects.filter(
                module__in=learning_modules, counted=True, is_published=True
            ).order_by("module__number", "pk")
        )
        pretest_assessment = programme.get_assessment(ProgrammeAssessmentKind.PRETEST)
        final_assessment = programme.get_assessment(ProgrammeAssessmentKind.FINAL)

        # 4. Allocate learners per batch
        created_learners = []
        source_idx = 0

        for b_conf in BATCH_CONFIG:
            batch, config = db_batches[b_conf["code"]]
            stage = config["stage"]
            batch_target = shares[b_conf["code"]]
            self.stdout.write(
                f"Generating {b_conf['code']} ({b_conf['name']}) -> {batch_target} learners..."
            )

            for _i in range(batch_target):
                if source_idx < len(learners_source):
                    entry = learners_source[source_idx]
                    cert_name = entry["name"]
                    email = entry["email"]
                else:
                    first_name, last_name = (
                        FIRST_NAMES[source_idx % len(FIRST_NAMES)],
                        LAST_NAMES[source_idx % len(LAST_NAMES)],
                    )
                    cert_name = f"{first_name} {last_name}"
                    # Derived from the learner's position only, so it is distinct for every
                    # learner and the same on every rerun, whatever the RNG did before.
                    email = (
                        f"{first_name.lower()}.{last_name.lower()}.{source_idx + 1:04d}"
                        f"@{SYNTHETIC_EMAIL_DOMAIN}"
                    )

                source_idx += 1

                # Date of birth between 1993 and 2005 (all >= 18)
                dob = date(1994, 1, 1) + timedelta(days=rng.randint(0, 4000))

                # Language distribution: 55% en, 23% hi, 15% mr, 7% gu
                lang_pick = rng.random()
                if lang_pick < 0.55:
                    pref_lang = "en"
                elif lang_pick < 0.78:
                    pref_lang = "hi"
                elif lang_pick < 0.93:
                    pref_lang = "mr"
                else:
                    pref_lang = "gu"

                # Signup date jitter within opens_at -> start_date
                base_time = config["opens_at"] + timedelta(
                    days=rng.randint(1, 12),
                    hours=rng.randint(8, 20),
                    minutes=rng.randint(0, 59),
                )

                with transaction.atomic():
                    user, user_created = User.objects.get_or_create(
                        email=email,
                        defaults={
                            "role": Role.LEARNER,
                            "status": UserStatus.ACTIVE,
                            "is_active": True,
                        },
                    )
                    if not user_created and not self._is_cohort_account(user):
                        raise CommandError(
                            f"{email} already belongs to an account that is not a cohort learner; "
                            "refusing to modify or move it."
                        )
                    if user_created:
                        user.set_unusable_password()
                        user.save(update_fields=["password"])

                    # Must use update() because auto_now_add=True ignores model.save()
                    User.objects.filter(pk=user.pk).update(created_at=base_time)

                    EmailAddress.objects.get_or_create(
                        user=user, email=email, defaults={"primary": True, "verified": True}
                    )
                    Profile.objects.get_or_create(
                        user=user,
                        defaults={
                            "certificate_name": cert_name,
                            "date_of_birth": dob,
                            "preferred_language": pref_lang,
                        },
                    )
                    enrol, _ = Enrolment.objects.get_or_create(
                        user=user,
                        defaults={"batch": batch},
                    )
                    # Must use update() to bypass auto_now_add on joined_at and created_at
                    Enrolment.objects.filter(pk=enrol.pk).update(
                        batch=batch, joined_at=base_time, created_at=base_time
                    )

                    if user_created or Attempt.objects.filter(user=user).count() == 0:
                        # Create behavioral activity matching stage
                        self._populate_activity(
                            user=user,
                            stage=stage,
                            base_time=base_time,
                            learning_modules=learning_modules,
                            all_units=all_units,
                            counted_parts=counted_parts,
                            pretest_assessment=pretest_assessment,
                            final_assessment=final_assessment,
                            rng=rng,
                        )

                created_learners.append(
                    {
                        "id": user.id,
                        "email": email,
                        "name": cert_name,
                        "batch": b_conf["code"],
                        "stage": stage,
                    }
                )

        # Write manifest
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": timezone.now().isoformat(),
                    "total_count": len(created_learners),
                    "batches": [b["code"] for b in BATCH_CONFIG],
                    "learners": created_learners,
                },
                f,
                indent=2,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCohort generation successful! Generated {len(created_learners)} learners across 5 cohorts.\n"
                f"Tracking manifest saved to: {MANIFEST_PATH}"
            )
        )

    def _load_roster(self):
        """Read and check the learner roster; nothing is written until it is all valid."""
        if not DATA_FILE_PATH.exists():
            return []
        with open(DATA_FILE_PATH, encoding="utf-8") as f:
            roster = json.load(f)
        if not isinstance(roster, list):
            raise CommandError(f"{DATA_FILE_PATH.name} must hold a list of learners.")
        seen = set()
        for n, entry in enumerate(roster, start=1):
            if not isinstance(entry, dict):
                raise CommandError(f"{DATA_FILE_PATH.name}: entry {n} is not an object.")
            email = str(entry.get("email") or "").strip().lower()
            name = str(entry.get("name") or "").strip()
            if not email or "@" not in email or not name:
                raise CommandError(f"{DATA_FILE_PATH.name}: entry {n} needs a name and an email.")
            if email in seen:
                raise CommandError(f"{DATA_FILE_PATH.name}: duplicate email {email} (entry {n}).")
            seen.add(email)
            entry["email"] = email
            entry["name"] = name
        return roster

    @staticmethod
    def _is_cohort_account(user):
        """An existing account may be reused only if it is a learner already in a cohort batch
        (or in none yet); never a staff account or a learner of another batch."""
        if user.role != Role.LEARNER or user.is_staff or user.is_superuser:
            return False
        enrolment = Enrolment.objects.filter(user=user).select_related("batch").first()
        return enrolment is None or enrolment.batch.code in {b["code"] for b in BATCH_CONFIG}

    def _ensure_course_content(self):
        """Ensure modules 1-9 have units, authentic CCFR curriculum questions, and published counted assessment parts."""
        CURRICULUM_QUESTIONS = {
            # Module 1: Account Security & Cyber Hygiene
            (1, 1): {
                "stem": "A victim reports that someone has logged into their social media account from an unknown location. What is the very first step the First Responder should advise?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Log out of all active sessions and change the password immediately with two-factor authentication enabled.",
                    },
                    {
                        "id": "o2",
                        "text": "Wait 24 hours to observe if any unauthorized messages are posted.",
                    },
                    {
                        "id": "o3",
                        "text": "Delete the social media account permanently without signing out.",
                    },
                    {
                        "id": "o4",
                        "text": "Post a public status update warning contacts that the profile is compromised.",
                    },
                ],
                "correct": "o1",
                "hint": "Immediate session termination and credential rotation stop ongoing unauthorized access.",
            },
            (1, 2): {
                "stem": "Why is a passkey considered significantly more secure than an SMS-based OTP for account login?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Passkeys use cryptographic key pairs bound to the domain, making them immune to phishing and SIM swapping.",
                    },
                    {
                        "id": "o2",
                        "text": "Passkeys are transmitted through unencrypted telecom satellite frequencies.",
                    },
                    {
                        "id": "o3",
                        "text": "Passkeys require the user to change their master password every 30 days.",
                    },
                    {"id": "o4", "text": "Passkeys only function on public desktop computers."},
                ],
                "correct": "o1",
                "hint": "FIDO2/WebAuthn passkeys cannot be intercepted or phished through fraudulent clone websites.",
            },
            (1, 3): {
                "stem": "What is the primary security benefit of enabling Two-Step Verification on WhatsApp?",
                "options": [
                    {
                        "id": "o1",
                        "text": "It requires a personalized 6-digit PIN when registering the phone number on a new device, preventing SIM hijacking.",
                    },
                    {
                        "id": "o2",
                        "text": "It automatically records and transcribes all voice and video calls.",
                    },
                    {
                        "id": "o3",
                        "text": "It hides the user's online status from all contacts permanently.",
                    },
                    {
                        "id": "o4",
                        "text": "It deletes stored chat backups every 7 days automatically.",
                    },
                ],
                "correct": "o1",
                "hint": "The custom 6-digit PIN prevents account takeover even if an attacker intercepts the SMS verification code.",
            },
            (1, 4): {
                "stem": "Which practice is recommended for securely managing multiple complex online passwords?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Use a reputable password manager with a strong master passphrase and encrypted offline backup.",
                    },
                    {
                        "id": "o2",
                        "text": "Use the same strong password across all personal and banking accounts.",
                    },
                    {
                        "id": "o3",
                        "text": "Store passwords in a plain text file saved directly on the computer desktop.",
                    },
                    {
                        "id": "o4",
                        "text": "Write passwords on a paper sticky note attached to the monitor frame.",
                    },
                ],
                "correct": "o1",
                "hint": "Password managers generate, store, and encrypt unique, high-entropy credentials for every service.",
            },
            (1, 5): {
                "stem": "When configuring account recovery options, what is the safest guideline to follow?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Ensure recovery phone numbers and email addresses are actively accessible and separate from shared devices.",
                    },
                    {
                        "id": "o2",
                        "text": "Use a shared departmental email address as the primary personal recovery email.",
                    },
                    {
                        "id": "o3",
                        "text": "Never configure recovery details so that potential attackers cannot see them.",
                    },
                    {
                        "id": "o4",
                        "text": "Send backup recovery codes over social media direct messages for safekeeping.",
                    },
                ],
                "correct": "o1",
                "hint": "Dedicated, private recovery channels ensure legitimate access can be restored quickly during account lockouts.",
            },
            # Module 2: Network & Mobile Threat Triage
            (2, 1): {
                "stem": "When connecting a smartphone or laptop to a public Wi-Fi network at a railway station, which measure provides essential transport security?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Use an encrypted VPN tunnel and disable local file sharing and network auto-connect.",
                    },
                    {
                        "id": "o2",
                        "text": "Accept all SSL certificate warnings that appear in the web browser.",
                    },
                    {
                        "id": "o3",
                        "text": "Disable the device host firewall to maximize network transfer throughput.",
                    },
                    {
                        "id": "o4",
                        "text": "Turn off the device screen lock while browsing public hotspots.",
                    },
                ],
                "correct": "o1",
                "hint": "VPN encryption protects payload traffic from Man-in-the-Middle (MitM) eavesdropping on open public Wi-Fi.",
            },
            (2, 2): {
                "stem": "A community member notices their mobile network signal suddenly drops to 'No Service', and shortly after, net banking alerts arrive. What threat does this indicate?",
                "options": [
                    {
                        "id": "o1",
                        "text": "A fraudulent SIM swap attack orchestrated to intercept SMS OTPs and banking tokens.",
                    },
                    {
                        "id": "o2",
                        "text": "Routine local cell tower maintenance by the telecommunications operator.",
                    },
                    {"id": "o3", "text": "A software bug in the smartphone battery firmware."},
                    {
                        "id": "o4",
                        "text": "The mobile device entering low-battery power saving mode.",
                    },
                ],
                "correct": "o1",
                "hint": "SIM swapping allows threat actors to re-assign a phone number to their own SIM card to steal 2FA OTPs.",
            },
            (2, 3): {
                "stem": "What is the security risk associated with keeping mobile Bluetooth in 'Discoverable' mode continuously in crowded public venues?",
                "options": [
                    {
                        "id": "o1",
                        "text": "It exposes the device to unauthorized pairing attacks, wireless tracking, and Bluebugging.",
                    },
                    {
                        "id": "o2",
                        "text": "It permanently deactivates the smartphone camera module.",
                    },
                    {
                        "id": "o3",
                        "text": "It triggers an unprompted factory data reset on the mobile phone.",
                    },
                    {
                        "id": "o4",
                        "text": "It blocks incoming cellular phone calls from numbers not saved in contacts.",
                    },
                ],
                "correct": "o1",
                "hint": "Continuous Bluetooth discoverability advertises device presence to nearby malicious scanners and wireless exploits.",
            },
            (2, 4): {
                "stem": "Which URL indicator confirms that an active web browsing session is protected by TLS encryption?",
                "options": [
                    {
                        "id": "o1",
                        "text": "The URL begins with 'https://' and the browser displays a valid, trusted security padlock icon.",
                    },
                    {
                        "id": "o2",
                        "text": "The webpage features an embedded banner claiming '100% Certified Safe'.",
                    },
                    {"id": "o3", "text": "The website address ends with '.html' or '.php'."},
                    {
                        "id": "o4",
                        "text": "The webpage contains a copyright statement at the bottom.",
                    },
                ],
                "correct": "o1",
                "hint": "HTTPS and valid TLS certificates encrypt browser-server communication against tampering and snooping.",
            },
            (2, 5): {
                "stem": "A victim receives an SMS claiming an urgent power bill is unpaid, warning of power disconnection in 30 minutes. What attack pattern is this?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Smishing (SMS Phishing) designed to create artificial panic and execute financial fraud.",
                    },
                    {
                        "id": "o2",
                        "text": "A standard automated notification from the state electricity distribution board.",
                    },
                    {
                        "id": "o3",
                        "text": "A DNS spoofing incident originating from the local home router.",
                    },
                    {"id": "o4", "text": "An operating system crash notification."},
                ],
                "correct": "o1",
                "hint": "Smishing campaigns use high-urgency threats like utility disconnection to manipulate victims into calling scam numbers.",
            },
            # Module 3: Malware Identification & Device Triage
            (3, 1): {
                "stem": "A workstation displays a ransom note stating all local office files are encrypted (.locked extension). What is the critical immediate triage action?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Immediately disconnect the network cable and turn off Wi-Fi to stop lateral propagation across the LAN.",
                    },
                    {
                        "id": "o2",
                        "text": "Power off the workstation by unplugging the wall socket immediately.",
                    },
                    {
                        "id": "o3",
                        "text": "Click the ransom note hyperlink to negotiate payment with the threat actors.",
                    },
                    {
                        "id": "o4",
                        "text": "Run a disk defragmentation utility to restore the encrypted sectors.",
                    },
                ],
                "correct": "o1",
                "hint": "Network isolation contains ransomware from spreading to network shares while preserving memory for forensic triage.",
            },
            (3, 2): {
                "stem": "Why should an infected computer NOT be powered off abruptly at the wall socket if digital forensics may be required?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Power severance destroys volatile RAM, losing active malware processes, decryption keys, and open network sockets.",
                    },
                    {
                        "id": "o2",
                        "text": "Abrupt power disconnection permanently damages the CPU processor silicon.",
                    },
                    {
                        "id": "o3",
                        "text": "Antivirus software requires continuous power for 48 hours to quarantine infected files.",
                    },
                    {
                        "id": "o4",
                        "text": "The ransomware program will immediately double its ransom demand upon reboot.",
                    },
                ],
                "correct": "o1",
                "hint": "RAM stores essential volatile evidence that is lost permanently once electrical power is interrupted.",
            },
            (3, 3): {
                "stem": "A user downloaded what appeared to be a media file named 'project_video.mp4.exe'. What does this double extension indicate?",
                "options": [
                    {
                        "id": "o1",
                        "text": "An executable malware program masquerading as a video file to trick the user into launching it.",
                    },
                    {
                        "id": "o2",
                        "text": "A high-efficiency video compression format recognized by standard media players.",
                    },
                    {
                        "id": "o3",
                        "text": "A backup restore checkpoint created by the Windows operating system.",
                    },
                    {
                        "id": "o4",
                        "text": "A subtitle file that can be opened safely with double-click.",
                    },
                ],
                "correct": "o1",
                "hint": "Attackers exploit hidden file extensions in Windows by appending fake extensions to executable (.exe) files.",
            },
            (3, 4): {
                "stem": "What is a prominent behavioral indicator of stalkerware or spyware running on a mobile smartphone?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Rapid abnormal battery drain, device overheating while idle, and unexplained high background data consumption.",
                    },
                    {
                        "id": "o2",
                        "text": "The phone screen brightness adjusting automatically under bright outdoor lighting.",
                    },
                    {
                        "id": "o3",
                        "text": "The device connecting automatically to saved home Wi-Fi networks.",
                    },
                    {"id": "o4", "text": "The phone ringtone volume decreasing when picked up."},
                ],
                "correct": "o1",
                "hint": "Stalkerware operates continuous background processes for location tracking, microphone streaming, and keystroke logging.",
            },
            (3, 5): {
                "stem": "When inspecting a suspected compromised Android device, which system settings section should be audited first?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Check 'Device admin apps', Accessibility service permissions, and 'Install unknown apps' authorizations.",
                    },
                    {
                        "id": "o2",
                        "text": "Change the default system font family to a serif typeface.",
                    },
                    {"id": "o3", "text": "Enable dark mode across all installed applications."},
                    {"id": "o4", "text": "Clear the browser download history cache."},
                ],
                "correct": "o1",
                "hint": "Malicious applications abuse Accessibility and Device Administrator privileges to capture screens and block uninstallation.",
            },
            # Module 4: Digital Evidence Handling & Chain of Custody
            (4, 1): {
                "stem": "A victim of online banking fraud wants to report to law enforcement. How should transaction records be preserved from the banking app?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Capture clear screenshots displaying the full Transaction ID, UTR number, recipient account/UPI ID, date, and exact timestamp.",
                    },
                    {
                        "id": "o2",
                        "text": "Write the transferred amount on a paper notebook and uninstall the mobile banking app.",
                    },
                    {
                        "id": "o3",
                        "text": "Forward the bank transaction SMS to a personal contact and delete the original message.",
                    },
                    {"id": "o4", "text": "Photograph the physical bank passbook cover only."},
                ],
                "correct": "o1",
                "hint": "The Unique Transaction Reference (UTR) and precise timestamp are critical for banks and police to freeze illicit funds.",
            },
            (4, 2): {
                "stem": "What is the primary legal objective of maintaining a strict 'Chain of Custody' for digital evidence?",
                "options": [
                    {
                        "id": "o1",
                        "text": "To provide a documented, tamper-evident record of everyone who collected, handled, transferred, and stored the evidence.",
                    },
                    {
                        "id": "o2",
                        "text": "To guarantee that the victim will receive immediate financial compensation from the court.",
                    },
                    {
                        "id": "o3",
                        "text": "To list the software programming tools used to develop the evidence analysis workstation.",
                    },
                    {
                        "id": "o4",
                        "text": "To establish an insurance valuation for seized computer equipment.",
                    },
                ],
                "correct": "o1",
                "hint": "A rigorous chain of custody proves evidence integrity and authenticity so that evidence remains admissible in court.",
            },
            (4, 3): {
                "stem": "When securing a mobile smartphone as evidence at an incident scene, why should it be placed in a Faraday bag or kept in Airplane Mode?",
                "options": [
                    {
                        "id": "o1",
                        "text": "To block radio signals and prevent remote wipe, remote locking, or incoming data alteration.",
                    },
                    {
                        "id": "o2",
                        "text": "To preserve the smartphone battery charge for laboratory analysis.",
                    },
                    {
                        "id": "o3",
                        "text": "To prevent the smartphone display from gathering dust particles.",
                    },
                    {
                        "id": "o4",
                        "text": "To accelerate forensic extraction speeds during forensic imaging.",
                    },
                ],
                "correct": "o1",
                "hint": "Faraday shielding blocks cellular, Wi-Fi, and Bluetooth signals, preventing remote deletion commands.",
            },
            (4, 4): {
                "stem": "Under Section 65B of the Indian Evidence Act (and Section 63 of Bharatiya Sakshya Adhiniyam), what certificate is required for electronic evidence?",
                "options": [
                    {
                        "id": "o1",
                        "text": "A signed certificate identifying the electronic record, describing the production device, and affirming lawful operational control.",
                    },
                    {
                        "id": "o2",
                        "text": "A handwritten document signed by three local neighborhood witnesses.",
                    },
                    {
                        "id": "o3",
                        "text": "A notarized photocopy of the device retail purchase bill.",
                    },
                    {
                        "id": "o4",
                        "text": "An oral testimony delivered by an internet service provider engineer.",
                    },
                ],
                "correct": "o1",
                "hint": "A 65B/63 BSA certificate certifies the authenticity and uninterrupted operational custody of electronic computer outputs.",
            },
            (4, 5): {
                "stem": "A victim has received abusive messages on WhatsApp that the sender is beginning to delete. How should the First Responder preserve the communication?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Use WhatsApp's 'Export Chat' (with media) feature and capture timestamped screenshots of profile info and phone numbers.",
                    },
                    {
                        "id": "o2",
                        "text": "Delete the entire conversation thread to protect the victim from emotional distress.",
                    },
                    {
                        "id": "o3",
                        "text": "Block the sender and immediately clear all chat records from the phone storage.",
                    },
                    {
                        "id": "o4",
                        "text": "Copy and paste the text of the messages into a personal note-taking application.",
                    },
                ],
                "correct": "o1",
                "hint": "Official chat exports retain cryptographic metadata and timestamps essential for criminal investigation.",
            },
            # Module 5: Social Engineering & Financial Scams
            (5, 1): {
                "stem": "A victim receives a call from a purported bank executive demanding they install 'AnyDesk' or 'TeamViewer' to complete urgent KYC. What is the attack goal?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Remote access fraud: viewing the victim's screen to intercept banking credentials and authorize fraudulent fund transfers.",
                    },
                    {
                        "id": "o2",
                        "text": "A standard customer support diagnostic procedure endorsed by the Reserve Bank of India.",
                    },
                    {
                        "id": "o3",
                        "text": "An automated system optimization procedure for mobile devices.",
                    },
                    {"id": "o4", "text": "A mandatory telecom network frequency re-calibration."},
                ],
                "correct": "o1",
                "hint": "Legitimate banking institutions never ask customers to download screen-sharing or remote desktop tools for KYC.",
            },
            (5, 2): {
                "stem": "On an online marketplace, a buyer sends a QR code to a seller claiming: 'Scan this code to receive your advance payment'. What happens if scanned with a UPI PIN?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Money is immediately deducted from the seller's account; receiving money via UPI never requires entering a UPI PIN.",
                    },
                    {
                        "id": "o2",
                        "text": "The seller's account is credited with the payment plus an instant verification bonus.",
                    },
                    {
                        "id": "o3",
                        "text": "The QR code verifies the seller's postal delivery address with the merchant portal.",
                    },
                    {
                        "id": "o4",
                        "text": "The transaction pauses until the buyer confirms physical item receipt.",
                    },
                ],
                "correct": "o1",
                "hint": "Golden Rule of UPI: Entering your UPI PIN always authorizes money to LEAVE your account, never to receive money.",
            },
            (5, 3): {
                "stem": "An employee receives an email purportedly from the company CEO demanding an immediate confidential wire transfer. What attack vector is this?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Business Email Compromise (BEC) / CEO Fraud exploiting organizational hierarchy and artificial urgency.",
                    },
                    {"id": "o2", "text": "A distributed denial-of-service (DDoS) packet flood."},
                    {
                        "id": "o3",
                        "text": "An automated human resources payroll calculation broadcast.",
                    },
                    {"id": "o4", "text": "A routine accounting database ledger synchronisation."},
                ],
                "correct": "o1",
                "hint": "BEC scams leverage spoofed executive identities and manufactured crises to bypass financial approval controls.",
            },
            (5, 4): {
                "stem": "What is the defining hallmark of a 'Digital Arrest' cyber scam commonly reported across India?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Fraudsters pose as police, CBI, or customs officials via video calls, holding victims in continuous intimidation and demanding money.",
                    },
                    {
                        "id": "o2",
                        "text": "A formal court summons served through verified registered postal service.",
                    },
                    {
                        "id": "o3",
                        "text": "An automated electronic traffic violation notice issued by highway cameras.",
                    },
                    {
                        "id": "o4",
                        "text": "A court appearance notice delivered by uniformed police officers.",
                    },
                ],
                "correct": "o1",
                "hint": "No Indian police or investigative agency conducts 'digital arrests' or interrogates suspects via video calls.",
            },
            (5, 5): {
                "stem": "What is the very first emergency action a Cyber First Responder should advise a financial cyber fraud victim to take?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Immediately dial the 1930 National Cyber Crime helpline and log the incident on cybercrime.gov.in within the Golden Hour.",
                    },
                    {
                        "id": "o2",
                        "text": "Call the scammer's phone number repeatedly to negotiate a refund.",
                    },
                    {
                        "id": "o3",
                        "text": "Wait for 3 working days to check if the bank automatically reverses the charge.",
                    },
                    {
                        "id": "o4",
                        "text": "Write a complaint on public social media comment threads.",
                    },
                ],
                "correct": "o1",
                "hint": "Reporting within the Golden Hour enables the 1930 network to freeze funds in the banking system before cash withdrawal.",
            },
            # Module 6: Operating System & Application Hygiene
            (6, 1): {
                "stem": "Why is sideloading modded applications (such as 'GB WhatsApp' or cracked games) from unofficial APK sites extremely dangerous?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Modded APKs frequently contain embedded keyloggers, remote access trojans, and malicious backdoors that bypass app store review.",
                    },
                    {
                        "id": "o2",
                        "text": "Modded APKs reduce smartphone screen resolution by 50% permanently.",
                    },
                    {
                        "id": "o3",
                        "text": "Modded APKs only connect to 2G networks and refuse to work on 5G.",
                    },
                    {
                        "id": "o4",
                        "text": "Modded APKs automatically translate all text into Latin.",
                    },
                ],
                "correct": "o1",
                "hint": "Unofficial modded applications bypass security review mechanisms and often harvest credentials, chats, and banking tokens.",
            },
            (6, 2): {
                "stem": "What is the primary security imperative behind applying operating system security updates promptly?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Updates patch known software vulnerabilities that threat actors actively weaponize for automated exploitation.",
                    },
                    {
                        "id": "o2",
                        "text": "Updates delete all old user documents to free up storage space.",
                    },
                    {
                        "id": "o3",
                        "text": "Updates are required in order to change desktop background pictures.",
                    },
                    {
                        "id": "o4",
                        "text": "Updates prevent the computer from receiving international emails.",
                    },
                ],
                "correct": "o1",
                "hint": "Unpatched security flaws leave systems open to automated exploit kits, worms, and zero-day attack campaigns.",
            },
            (6, 3): {
                "stem": "A flashlight mobile utility requests permissions for 'Read Contacts', 'Record Audio', and 'Access Location'. What should the user do?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Deny the unnecessary permissions and uninstall the app; utility tools have no legitimate need for sensitive personal data.",
                    },
                    {
                        "id": "o2",
                        "text": "Grant all permissions to ensure the flashlight illuminates at maximum brightness.",
                    },
                    {"id": "o3", "text": "Grant permissions only during nighttime hours."},
                    {"id": "o4", "text": "Share the app with family members to test their phones."},
                ],
                "correct": "o1",
                "hint": "Excessive, disproportionate permissions on basic utility apps are a primary indicator of spyware and data harvesters.",
            },
            (6, 4): {
                "stem": "What critical protection is provided by enabling Full Disk Encryption (e.g., BitLocker or FileVault)?",
                "options": [
                    {
                        "id": "o1",
                        "text": "It prevents unauthorized data extraction if the physical laptop, drive, or device is lost, stolen, or disassembled.",
                    },
                    {
                        "id": "o2",
                        "text": "It filters incoming phishing emails from entering the inbox.",
                    },
                    {
                        "id": "o3",
                        "text": "It prevents hardware components from overheating during video rendering.",
                    },
                    {"id": "o4", "text": "It doubles broadband connection speeds on home Wi-Fi."},
                ],
                "correct": "o1",
                "hint": "Full disk encryption ensures data at rest cannot be accessed by mounting the drive on an external computer.",
            },
            (6, 5): {
                "stem": "When an employee or volunteer departs an organisation, which account hygiene protocol must be completed immediately?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Revoke all institutional credentials, disable VPN/cloud access, and execute a secure remote wipe of organizational data.",
                    },
                    {
                        "id": "o2",
                        "text": "Permit the user to retain active passwords for an additional 60 days.",
                    },
                    {
                        "id": "o3",
                        "text": "Forward all incoming corporate communications to the former user's personal email.",
                    },
                    {"id": "o4", "text": "Shut down the corporate email server for one week."},
                ],
                "correct": "o1",
                "hint": "Timely access revocation eliminates lingering credentials and protects institutional assets from unauthorized exposure.",
            },
            # Module 7: Online Harassment, Stalking & Gender Safety
            (7, 1): {
                "stem": "A victim reports that a malicious actor has created a fake profile using her photos and is sending obscene messages. What is the immediate First Response?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Preserve evidence (profile URL, handle, screenshots) and submit reports through platform impersonation channels and cybercrime.gov.in.",
                    },
                    {
                        "id": "o2",
                        "text": "Engage in an aggressive confrontation with the impersonator in public comment sections.",
                    },
                    {
                        "id": "o3",
                        "text": "Delete her authentic profile and perform a factory reset on her smartphone.",
                    },
                    {
                        "id": "o4",
                        "text": "Pay the impersonator the demanded extortion sum to remove the profile.",
                    },
                ],
                "correct": "o1",
                "hint": "Documenting exact URLs and handles before takedown ensures investigative agencies can request IP logs from platforms.",
            },
            (7, 2): {
                "stem": "Which platform initiative allows individuals to prevent the online dissemination of non-consensual intimate images (NCII)?",
                "options": [
                    {
                        "id": "o1",
                        "text": "StopNCII.org, which creates privacy-preserving perceptual hashes locally on the device without uploading original photos.",
                    },
                    {
                        "id": "o2",
                        "text": "Uploading raw original photographs to public web forums for community moderation.",
                    },
                    {
                        "id": "o3",
                        "text": "Forwarding original photographs to all personal contacts as a warning advisory.",
                    },
                    {"id": "o4", "text": "Changing the residential Wi-Fi network password."},
                ],
                "correct": "o1",
                "hint": "StopNCII generates unique digital fingerprints (hashes) on the user device to block matching uploads across tech platforms.",
            },
            (7, 3): {
                "stem": "Which legal provision under the Information Technology Act 2000 penalizes publishing or transmitting sexually explicit material in electronic form?",
                "options": [
                    {"id": "o1", "text": "Section 67 and Section 67A of the IT Act 2000."},
                    {"id": "o2", "text": "Section 43A of the Motor Vehicles Act."},
                    {"id": "o3", "text": "Section 12 of the Indian Telegraph Act 1885."},
                    {"id": "o4", "text": "Section 138 of the Negotiable Instruments Act."},
                ],
                "correct": "o1",
                "hint": "Sections 67 and 67A prescribe rigorous imprisonment and fines for publishing or transmitting obscene or sexually explicit electronic content.",
            },
            (7, 4): {
                "stem": "A student is experiencing persistent online stalking with the perpetrator tracking their daily physical check-ins. What immediate advice should be given?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Audit social privacy settings, turn off app location permissions, cease real-time check-ins, and preserve all threatening logs.",
                    },
                    {
                        "id": "o2",
                        "text": "Broadcast future travel itineraries publicly to demonstrate defiance.",
                    },
                    {
                        "id": "o3",
                        "text": "Share continuous live location updates with all followers.",
                    },
                    {
                        "id": "o4",
                        "text": "Disconnect household electricity power during daylight hours.",
                    },
                ],
                "correct": "o1",
                "hint": "Disabling location metadata and eliminating public check-ins prevents digital stalking from escalating into physical danger.",
            },
            (7, 5): {
                "stem": "Why must a Cyber First Responder maintain an empathetic, non-judgmental attitude when assisting victims of cyber harassment or sextortion?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Victim-blaming creates acute psychological trauma, leading victims to conceal critical evidence or succumb to extortion demands.",
                    },
                    {
                        "id": "o2",
                        "text": "It is a mandatory prerequisite to charge commercial advisory fees.",
                    },
                    {
                        "id": "o3",
                        "text": "It allows the First Responder to assume permanent ownership of the victim's social profiles.",
                    },
                    {
                        "id": "o4",
                        "text": "It legally obligates the platform to shut down within 24 hours.",
                    },
                ],
                "correct": "o1",
                "hint": "Non-judgmental psychological first aid reassures the victim, prevents self-harm, and facilitates orderly evidence gathering.",
            },
            # Module 8: Incident Reporting & Legal Frameworks
            (8, 1): {
                "stem": "What is the dedicated national toll-free helpline number in India for immediate citizen assistance in reporting cyber financial fraud?",
                "options": [
                    {"id": "o1", "text": "1930"},
                    {"id": "o2", "text": "1091"},
                    {"id": "o3", "text": "100"},
                    {"id": "o4", "text": "112"},
                ],
                "correct": "o1",
                "hint": "The 1930 helpline connects citizens directly to the Citizen Financial Cyber Fraud Reporting and Management System (CFCFRMS).",
            },
            (8, 2): {
                "stem": "What is the official Government of India portal for filing cybercrime complaints, particularly those involving women and children?",
                "options": [
                    {
                        "id": "o1",
                        "text": "cybercrime.gov.in (National Cyber Crime Reporting Portal)",
                    },
                    {"id": "o2", "text": "cyberpolice.com"},
                    {"id": "o3", "text": "reportfraud.gov.org"},
                    {"id": "o4", "text": "indiacyberhelpline.in"},
                ],
                "correct": "o1",
                "hint": "cybercrime.gov.in is the nodal national portal managed by the Indian Cyber Crime Coordination Centre (I4C), MHA.",
            },
            (8, 3): {
                "stem": "Under the CERT-In directions of April 2022, within what time must specified entities report the cyber incident types listed in Annexure I?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Within 6 hours of noticing the incident or being notified of it.",
                    },
                    {"id": "o2", "text": "Within 30 calendar days."},
                    {"id": "o3", "text": "Within 90 business days."},
                    {"id": "o4", "text": "Only upon completion of the annual corporate tax audit."},
                ],
                "correct": "o1",
                "hint": "CERT-In directions require specified organizations to report cybersecurity incidents within 6 hours to coordinate national defense.",
            },
            (8, 4): {
                "stem": "What principal protection is established under Section 43A of the Information Technology Act 2000?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Liability of body corporates to pay compensation for negligence in maintaining reasonable security practices regarding sensitive personal data.",
                    },
                    {
                        "id": "o2",
                        "text": "Mandatory life imprisonment for downloading copyrighted media files.",
                    },
                    {
                        "id": "o3",
                        "text": "Tax rebates for businesses purchasing commercial firewall hardware.",
                    },
                    {
                        "id": "o4",
                        "text": "Free broadband connectivity for rural cooperative societies.",
                    },
                ],
                "correct": "o1",
                "hint": "Section 43A mandates reasonable security practices and establishes civil liability for corporate data mishandling.",
            },
            (8, 5): {
                "stem": "Under the Digital Personal Data Protection (DPDP) Act 2023, who bears legal accountability for safeguarding personal data and reporting breaches?",
                "options": [
                    {
                        "id": "o1",
                        "text": "The Data Fiduciary (the entity determining the purpose and means of processing personal data).",
                    },
                    {"id": "o2", "text": "Only foreign offshore cloud service providers."},
                    {"id": "o3", "text": "Individual residential broadband subscribers."},
                    {"id": "o4", "text": "Computer hardware assembling factories."},
                ],
                "correct": "o1",
                "hint": "The DPDP Act 2023 holds Data Fiduciaries strictly liable for data security, breach notifications, and consumer rights.",
            },
            # Module 9: Community Incident Response & Crisis Handling
            (9, 1): {
                "stem": "What is the primary role and legal boundary of a certified Community Cyber First Responder (CCFR)?",
                "options": [
                    {
                        "id": "o1",
                        "text": "To provide initial triage, preserve volatile evidence, de-escalate emotional crisis, and facilitate formal reporting to authorities.",
                    },
                    {
                        "id": "o2",
                        "text": "To perform offensive counter-hacking into the suspect's computer systems.",
                    },
                    {
                        "id": "o3",
                        "text": "To execute independent search and seizure warrants on private property.",
                    },
                    {
                        "id": "o4",
                        "text": "To guarantee 100% money recovery in exchange for advance consulting fees.",
                    },
                ],
                "correct": "o1",
                "hint": "First Responders act as community facilitators and evidence preservation aides, never as vigilantes or police replacements.",
            },
            (9, 2): {
                "stem": "A community member experiencing financial cyber fraud is in severe panic and emotional distress. What should the Responder do first?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Calm the victim, listen patiently without judgment, provide reassurance, and guide immediate triage (block cards, call 1930).",
                    },
                    {
                        "id": "o2",
                        "text": "Chide the victim for being gullible and sharing their banking OTP.",
                    },
                    {
                        "id": "o3",
                        "text": "Tell the victim that their savings are permanently lost and no action can help.",
                    },
                    {
                        "id": "o4",
                        "text": "Broadcast the victim's panic voice recordings across community chat groups.",
                    },
                ],
                "correct": "o1",
                "hint": "Calm, structured guidance reassures the victim and ensures immediate triage steps (blocking cards, dialing 1930) are taken.",
            },
            (9, 3): {
                "stem": "When helping a victim draft a formal cyber complaint for law enforcement, what narrative structure is recommended?",
                "options": [
                    {
                        "id": "o1",
                        "text": "A clear chronological timeline: initial contact method, fraudulent claims made, transaction details with UTRs, and evidence annexures.",
                    },
                    {
                        "id": "o2",
                        "text": "A theoretical essay discussing international internet history.",
                    },
                    {
                        "id": "o3",
                        "text": "Submitting only a smartphone screenshot without any explanatory text statement.",
                    },
                    {
                        "id": "o4",
                        "text": "A list of demands addressed to foreign technology companies.",
                    },
                ],
                "correct": "o1",
                "hint": "Precise chronological narratives accompanied by UTR numbers allow investigating officers to register FIRs and issue freeze notices.",
            },
            (9, 4): {
                "stem": "Why must a Cyber First Responder NEVER attempt to 'hack back' or deploy counter-exploits against an attacker's infrastructure?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Hacking back is an illegal offense under Section 66 of the IT Act, risks attacking innocent compromised intermediaries, and destroys evidence.",
                    },
                    {
                        "id": "o2",
                        "text": "Counter-hacking requires a specialized civilian aviation license.",
                    },
                    {
                        "id": "o3",
                        "text": "Attackers always deploy unhackable military-grade hardware.",
                    },
                    {"id": "o4", "text": "Counter-hacking consumes excess household bandwidth."},
                ],
                "correct": "o1",
                "hint": "Unauthorized access is a criminal act regardless of intent; counter-attacks destroy forensic integrity and admissibility.",
            },
            (9, 5): {
                "stem": "In community cyber awareness sessions, what is the most effective behavioral rule to teach citizens regarding unsolicited communications?",
                "options": [
                    {
                        "id": "o1",
                        "text": "Stop, Think, Verify: Never click unknown links, never share OTP/PINs, and independently verify claims through official contact numbers.",
                    },
                    {
                        "id": "o2",
                        "text": "Always click urgent notification links immediately before they expire.",
                    },
                    {
                        "id": "o3",
                        "text": "Share banking passwords with reliable neighbors for safekeeping.",
                    },
                    {
                        "id": "o4",
                        "text": "Keep mobile phones turned off throughout standard banking hours.",
                    },
                ],
                "correct": "o1",
                "hint": "The 'Stop, Think, Verify' habit neutralizes urgency-based psychological triggers used in phishing and social engineering.",
            },
        }

        for mod in Module.objects.filter(kind=ModuleKind.LEARNING, counted=True).order_by("number"):
            # 1. Units
            if Unit.objects.filter(module=mod).count() == 0:
                Unit.objects.create(
                    module=mod,
                    slug=f"module-{mod.number}-fundamentals",
                    order=1,
                    nominal_minutes=30,
                    type="reading",
                )
                Unit.objects.create(
                    module=mod,
                    slug=f"module-{mod.number}-incident-response",
                    order=2,
                    nominal_minutes=45,
                    type="reading",
                )

            # 2. Assessment Parts & Live Questions (5 questions per module)
            for q_idx in range(1, 6):
                stable_id = f"CCFR-M{mod.number:02d}-Q{q_idx:02d}"
                q_data = CURRICULUM_QUESTIONS.get((mod.number, q_idx))
                if q_data:
                    body = {
                        "stem": q_data["stem"],
                        "options": q_data["options"],
                        "correct": q_data["correct"],
                        "hint": q_data["hint"],
                        "gate": {},
                    }
                    q = Question.objects.filter(stable_id=stable_id).first()
                    if not q:
                        q = qservices.create_question(
                            stable_id=stable_id,
                            module=mod,
                            fmt="mcq",
                            body=body,
                            tags={"pc": "PC1"},
                            pool=Pool.MODULE_QUIZ,
                        )
                    else:
                        # Update question version with curriculum body
                        qservices.add_version(q, body)
                    if q.status != QuestionStatus.LIVE:
                        qservices.publish(q)

            # Reuse the module's configured counted parts; only bootstrap one for a module that
            # has none, creating and publishing it together so no unpublished draft is left.
            if not AssessmentPart.objects.filter(module=mod, counted=True).exists():
                with transaction.atomic():
                    part = AssessmentPart.objects.create(
                        module=mod,
                        name=f"Module {mod.number} Knowledge Check",
                        family=PartFamily.MCQ,
                        marks=100,
                        counted=True,
                        selection=Selection.ALL,
                        pool=Pool.MODULE_QUIZ,
                    )
                    publish_part(part)

        # Build memory caches for attempt items
        self.cached_part_questions = {}
        for p in AssessmentPart.objects.filter(pool=Pool.MODULE_QUIZ).select_related("module"):
            qs = Question.objects.filter(
                module=p.module,
                pool=p.pool,
                status=QuestionStatus.LIVE,
            ).order_by("stable_id")[:5]
            self.cached_part_questions[p.id] = [q.current_version for q in qs if q.current_version]

        self.cached_pretest_questions = []
        for m_num in range(1, 6):
            q = (
                Question.objects.filter(
                    module__number=m_num,
                    status=QuestionStatus.LIVE,
                )
                .order_by("stable_id")
                .first()
            )
            if q and q.current_version:
                self.cached_pretest_questions.append(q.current_version)

        self.cached_final_questions = []
        for m_num in range(1, 10):
            q = (
                Question.objects.filter(
                    module__number=m_num,
                    status=QuestionStatus.LIVE,
                )
                .order_by("stable_id")
                .first()
            )
            if q and q.current_version:
                self.cached_final_questions.append(q.current_version)
        extra_q = (
            Question.objects.filter(
                module__number=1,
                status=QuestionStatus.LIVE,
            )
            .order_by("stable_id")[1:2]
            .first()
        )
        if extra_q and extra_q.current_version:
            self.cached_final_questions.append(extra_q.current_version)

    def _populate_activity(
        self,
        user,
        stage,
        base_time,
        learning_modules,
        all_units,
        counted_parts,
        pretest_assessment,
        final_assessment,
        rng,
    ):
        """Simulate learning progress, time logs, and assessments based on cohort maturity."""
        now = timezone.now()

        # Dormant accounts in fresh/early stages (small slice)
        if stage == "fresh_enrolled" and rng.random() < 0.12:
            return

        # 1. Pre-test
        pretest_score = rng.randint(28, 56)
        self._record_attempt(
            user=user,
            prog_assessment=pretest_assessment,
            part=None,
            score=pretest_score,
            timestamp=base_time + timedelta(hours=rng.randint(2, 6)),
            duration_minutes=rng.randint(18, 35),
            rng=rng,
        )

        # Decide learner competence profile
        competence = rng.random()
        if competence < 0.25:
            profile_kind = "high"
        elif competence < 0.65:
            profile_kind = "solid"
        elif competence < 0.88:
            profile_kind = "borderline"
        else:
            profile_kind = "struggling"

        # Determine how many modules completed based on stage
        if stage in ("senior_complete", "mature_complete"):
            modules_to_complete = 9
            if stage == "senior_complete":
                target_end_time = datetime(2026, 10, 16, 16, 0, tzinfo=UTC) + timedelta(
                    days=rng.randint(-3, 2), hours=rng.randint(1, 6)
                )
            else:
                target_end_time = datetime(2026, 11, 4, 16, 0, tzinfo=UTC) + timedelta(
                    days=rng.randint(-3, 1), hours=rng.randint(1, 6)
                )
        elif stage == "mid_progress":  # CCFR-B04 (Active ongoing)
            modules_to_complete = rng.randint(4, 7)
            # Only ~4% are stuck (> 7 days inactive)
            is_stuck = (profile_kind == "struggling") or (rng.random() < 0.04)
            if is_stuck:
                target_end_time = now - timedelta(days=rng.randint(8, 16), hours=rng.randint(2, 8))
            else:
                target_end_time = now - timedelta(days=rng.randint(0, 3), hours=rng.randint(1, 10))
        elif stage == "early_progress":  # CCFR-B05
            modules_to_complete = rng.randint(1, 4)
            is_stuck = rng.random() < 0.03
            if is_stuck:
                target_end_time = now - timedelta(days=rng.randint(8, 12), hours=rng.randint(1, 6))
            else:
                target_end_time = now - timedelta(days=rng.randint(0, 2), hours=rng.randint(1, 8))
        else:  # fresh_enrolled: CCFR-B06
            modules_to_complete = rng.randint(0, 2)
            target_end_time = now - timedelta(days=rng.randint(0, 2), hours=rng.randint(1, 6))

        if modules_to_complete == 0:
            return

        # Activity must fit between enrolment and now; a short window means less activity.
        target_end_time = min(target_end_time, now)
        total_duration = (target_end_time - base_time).total_seconds()
        if total_duration <= 0:
            return
        step_seconds = total_duration / max(modules_to_complete, 1)

        # 2. Iterate through modules
        for mod_idx in range(modules_to_complete):
            mod_num = mod_idx + 1
            mod_time = base_time + timedelta(seconds=int(step_seconds * (mod_idx + 1)))
            mod_units = [u for u in all_units if u.module.number == mod_num]

            # Study units
            for u_idx, u in enumerate(mod_units):
                if u.published() is None:
                    continue  # no published content: nothing to complete or study
                u_time = mod_time - timedelta(
                    minutes=rng.randint(20, 60) * (len(mod_units) - u_idx)
                )
                study_minutes = rng.randint(u.nominal_minutes, int(u.nominal_minutes * 1.8))
                prog, _ = UnitProgress.objects.get_or_create(
                    user=user, unit=u, defaults={"completed_at": u_time}
                )
                UnitProgress.objects.filter(pk=prog.pk).update(
                    completed_at=u_time, created_at=u_time
                )
                TimeLog.objects.get_or_create(
                    user=user,
                    unit=u,
                    date=u_time.date(),
                    defaults={"seconds": study_minutes * 60},
                )

            # Module assessment parts
            mod_parts = [p for p in counted_parts if p.module.number == mod_num]
            for part in mod_parts:
                part_score = self._sample_score(profile_kind, rng)
                self._record_attempt(
                    user=user,
                    prog_assessment=None,
                    part=part,
                    score=part_score,
                    timestamp=mod_time,
                    duration_minutes=rng.randint(12, 28),
                    rng=rng,
                )

        # 3. Final Exam for mature cohorts
        if stage in ("senior_complete", "mature_complete") and modules_to_complete == 9:
            final_time = target_end_time + timedelta(
                days=rng.randint(1, 3), hours=rng.randint(2, 5)
            )
            fail_retry = (stage == "senior_complete" and rng.random() < 0.16) or (
                stage == "mature_complete" and rng.random() < 0.12
            )

            if fail_retry:
                # Attempt 1: Failed
                fail_score = rng.randint(38, 48)
                self._record_attempt(
                    user=user,
                    prog_assessment=final_assessment,
                    part=None,
                    score=fail_score,
                    timestamp=final_time,
                    duration_minutes=rng.randint(45, 62),
                    attempt_num=1,
                    rng=rng,
                )
                # Attempt 2: Passed 2 to 4 days later
                retry_time = final_time + timedelta(days=rng.randint(2, 4), hours=rng.randint(2, 5))
                pass_score = rng.randint(62, 78)
                self._record_attempt(
                    user=user,
                    prog_assessment=final_assessment,
                    part=None,
                    score=pass_score,
                    timestamp=retry_time,
                    duration_minutes=rng.randint(40, 55),
                    attempt_num=2,
                    rng=rng,
                )
            else:
                final_score = self._sample_score(profile_kind, rng)
                self._record_attempt(
                    user=user,
                    prog_assessment=final_assessment,
                    part=None,
                    score=final_score,
                    timestamp=final_time,
                    duration_minutes=rng.randint(38, 58),
                    attempt_num=1,
                    rng=rng,
                )

    def _sample_score(self, profile_kind, rng):
        ranges = {
            "high": (76, 94),
            "solid": (58, 74),
            "borderline": (50, 62),
            "struggling": (36, 52),
        }
        lo, hi = ranges[profile_kind]
        return rng.randint(lo, hi)

    def _record_attempt(
        self,
        user,
        prog_assessment,
        part,
        score,
        timestamp,
        duration_minutes,
        attempt_num=1,
        rng=None,
    ):
        """Record an attempt with AttemptItem rows if live questions are present."""
        started = timestamp - timedelta(minutes=duration_minutes)
        attempt = Attempt.objects.create(
            user=user,
            part=part,
            programme_assessment=prog_assessment,
            number=attempt_num,
            status=AttemptStatus.SUBMITTED,
            score=Decimal(str(score)),
            all_answered=True,
            gate_breached=False,
            counted=True,
            submitted_at=timestamp,
            last_saved_at=timestamp,
            created_at=started,
        )
        # Must use update() to bypass auto_now_add
        Attempt.objects.filter(pk=attempt.pk).update(
            started_at=started,
            last_saved_at=timestamp,
            created_at=started,
            submitted_at=timestamp,
        )

        # Attempt to create realistic AttemptItems using cached question versions
        target_questions = []
        if part:
            target_questions = getattr(self, "cached_part_questions", {}).get(part.id, [])
        elif prog_assessment and prog_assessment.kind == "pretest":
            target_questions = getattr(self, "cached_pretest_questions", [])
        elif prog_assessment and prog_assessment.kind == "final":
            target_questions = getattr(self, "cached_final_questions", [])

        if target_questions:
            items_to_create = []
            num_q = len(target_questions)
            # Calculate how many questions the learner answered correctly
            num_correct = int(
                (Decimal(score) * num_q / Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            )
            if score >= 50 and num_correct < (num_q + 1) // 2:
                num_correct = (num_q + 1) // 2

            actual_score = percent(Decimal(num_correct), Decimal(num_q))
            attempt.score = actual_score
            Attempt.objects.filter(pk=attempt.pk).update(score=actual_score)

            # Randomly select which questions are answered correctly
            if rng:
                correct_indices = set(rng.sample(range(num_q), num_correct))
            else:
                correct_indices = set(range(num_correct))

            for idx, qv in enumerate(target_questions):
                pos = idx + 1
                is_correct = idx in correct_indices
                fmt = qv.question.format
                body = qv.body

                try:
                    opt_map = formats.make_map(fmt, body, rng)
                except Exception as exc:
                    # Fail loudly: the learner's transaction rolls back rather than saving a
                    # made-up option map.
                    raise CommandError(
                        f"Could not build the option map for question version {qv.pk} "
                        f"({qv.question.stable_id}): {exc}"
                    ) from exc

                response = {}
                if fmt == "mcq" and isinstance(body, dict) and "correct" in body:
                    correct_key = body["correct"]
                    tokens = opt_map.get("tokens", {})
                    if is_correct:
                        choice_token = next(
                            (t for t, k in tokens.items() if k == correct_key), "t0"
                        )
                    else:
                        choice_token = next(
                            (t for t, k in tokens.items() if k != correct_key), "t1"
                        )
                    response = {"choice": choice_token}

                items_to_create.append(
                    AttemptItem(
                        attempt=attempt,
                        position=pos,
                        format=fmt,
                        question_version=qv,
                        points=Decimal("1.00"),
                        option_map=opt_map,
                        response=response,
                        score=Decimal("1.00") if is_correct else Decimal("0.00"),
                        gate_flag=False,
                    )
                )

            if items_to_create:
                AttemptItem.objects.bulk_create(items_to_create)

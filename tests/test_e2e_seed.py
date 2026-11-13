"""The journey and load-test seeds: invented data only, refuse production, clean up exactly."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.assessments import programme
from apps.assessments.models import AssessmentPart, ExamSet
from apps.batches.models import Batch
from apps.content.models import Module
from apps.questions.models import Question
from apps.results.policy import compute_results

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, *args):
    out = StringIO()
    call_command(name, *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def e2e_data_sandbox():
    from apps.core.e2e_data import SANDBOX_MODULE

    return SANDBOX_MODULE


def counts():
    return (
        User.objects.count(),
        Batch.objects.count(),
        AssessmentPart.objects.count(),
        Question.objects.count(),
        ExamSet.objects.count(),
    )


@pytest.mark.parametrize("module", ["config.settings.prod", "config.settings.base", ""])
def test_refuses_anything_but_dev_and_staging(monkeypatch, module):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
    for command in ("e2e_seed", "e2e_clean", "loadtest_seed"):
        with pytest.raises(CommandError, match="Refusing to run"):
            run(command)


def test_seed_builds_a_working_course_and_clean_removes_it():
    before = counts()
    manifest = json.loads(run("e2e_seed"))
    assert set(manifest["batches"]) == {"E2E-B01", "E2E-B02", "E2E-B03"}
    assert Batch.objects.get(code="E2E-B03").accepting
    assert not Batch.objects.get(code="E2E-B01").accepting

    ready = User.objects.get(email=manifest["users"]["final"])
    locked = User.objects.get(email=manifest["users"]["locked"])
    fresh = User.objects.get(email=manifest["users"]["fresh"])
    assert programme.final_locked_reasons(ready) == []  # the final is open
    assert programme.final_locked_reasons(locked)  # one part was submitted with blanks
    assert programme.final_locked_reasons(fresh)
    assert compute_results([ready.pk])[ready.pk].setup_gaps == []

    mentor = User.objects.get(email=manifest["users"]["mentor1"])
    assert mentor.authenticator_set.filter(type="totp").exists()
    assert mentor.mentored.count() == 2  # B01 and B03

    again = json.loads(run("e2e_seed"))  # safe to run twice
    assert again == manifest

    done = json.loads(run("e2e_clean"))
    assert done["users"] > 0
    assert counts() == before
    assert not Module.objects.filter(number=e2e_data_sandbox()).exists()


def test_clean_keeps_nothing_it_did_not_make():
    other = Batch.objects.create(code="REAL-1", name="A real batch")
    run("e2e_seed")
    done = json.loads(run("e2e_clean"))
    assert "kept" not in done  # the test database role owns its tables
    assert Batch.objects.filter(pk=other.pk).exists()
    assert not Batch.objects.filter(code__startswith="E2E-").exists()
    assert not ExamSet.objects.filter(code="E2EJ").exists()
    assert not Question.objects.filter(stable_id__startswith="E2EJ-").exists()

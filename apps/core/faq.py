"""Questions and answers for the help page and the landing page (Stage 9).

One list, so the two pages can never disagree. Text is plain (no HTML). It is lazily translated
(UI catalogue, gettext), and the answers repeat only decided rules: D3 attempts, D14 and D32
limits, D34 sign-in, D17 and D37 names, D36 certificates.
"""

from django.utils.translation import gettext_lazy as _

# (question, answer, on the landing page as well)
FAQ = [
    (
        _("Who can join?"),
        _(
            "Anyone aged 16 or over. If you are 16 or 17, a parent or guardian confirms by "
            "email before your account starts. Under-16s can't register."
        ),
        True,
    ),
    (
        _("How do I register?"),
        _(
            "Sign up with your own email address and pick a batch that is accepting "
            "registrations. Batches are opened by a mentor or the programme team. If none is "
            "open, ask your trainer."
        ),
        True,
    ),
    (
        _("Do I need to sign in to learn?"),
        _(
            "Yes. Films, readings, handouts and practice checks open after you sign in. Once "
            "you are in, nothing is locked: go in any order and come back any time."
        ),
        True,
    ),
    (
        _("What happens if I don't pass an assessment?"),
        _(
            "Nothing bad. Read the hints and try again. Your best attempt counts and the pass "
            "mark is 50%. Your batch may set a limit on attempts; if it does, you will see how "
            "many you have used."
        ),
        True,
    ),
    (
        _("How do I get my certificate?"),
        _(
            "When you are eligible, it appears on your dashboard after your mentor approves it, "
            "or at once if your batch has automatic issue on. Download it from the site. It is "
            "never sent by email. Certificates are in English and carry a QR code anyone can use "
            "to check them."
        ),
        True,
    ),
    (
        _("Why is my certificate name locked?"),
        _(
            "You type it once, in English letters, exactly as it should be printed. After that "
            "only your mentor or an admin can change it, and the change is logged."
        ),
        False,
    ),
    (
        _("How are modules marked?"),
        _(
            "Each module is worth 100 marks: Part A (multiple choice, 50) and Part B "
            "(interactive, 50). Your best attempt at each part counts and the pass mark is 50%."
        ),
        False,
    ),
    (
        _("What do I see after an assessment?"),
        _(
            "Your score, which questions were right or wrong, and a hint for each. Never the "
            "correct option, so the assessment stays fair for everyone."
        ),
        False,
    ),
    (
        _("What is a safety gate?"),
        _(
            "Some choices could put a person at risk, such as paying a ‘recovery agent’ "
            "or asking a victim to send a private image. If you make one, the attempt shows its "
            "score but does not count. Read the hint and try again."
        ),
        False,
    ),
    (
        _("When does the final unlock?"),
        _(
            "When you have taken the pre-test and submitted every counted part of every module "
            "with all questions answered. You do not need to have passed them yet."
        ),
        False,
    ),
    (
        _("Can I switch language?"),
        _(
            "Yes, any time, even during an assessment. Your answers are kept. Some "
            "translations are still drafts and are labelled."
        ),
        False,
    ),
    (
        _("I forgot my password"),
        _(
            "Use ‘Forgot your password?’ on the sign-in page. If you can't reach your "
            "email, your mentor can give you a one-time reset link that works for one hour."
        ),
        False,
    ),
]

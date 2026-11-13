from django import template
from django.templatetags.static import static
from django.utils import timezone
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name, size="", extra=""):
    """An inline SVG icon from the shared sprite (static/img/icons.svg).

    `size` is "sm" or "lg"; `extra` adds classes.
    """
    cls = " ".join(c for c in ("icon", f"icon--{size}" if size else "", extra) if c)
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="{}#i-{}"/></svg>',
        cls,
        static("img/icons.svg"),
        name,
    )


@register.filter
def initials(value):
    """'Asha R. Desai' -> 'AR'."""
    return "".join(word[0] for word in str(value).split()[:2]).upper()


@register.filter
def pct(value):
    """Clamp a number to 0..100 for progress bars."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _widget_class(field):
    widget = field.field.widget
    name = type(widget).__name__
    if name in ("CheckboxInput", "RadioSelect", "CheckboxSelectMultiple", "HiddenInput"):
        return ""
    if name in ("Select", "SelectMultiple"):
        return "select"
    if name == "Textarea":
        return "textarea"
    return "input"


@register.filter
def as_input(field):
    """Render a form field's widget with the shared classes and accessibility attributes.

    Adds the prototype's `.input` / `.select` class, `aria-invalid` when there are errors and
    `aria-describedby` pointing at the hint and error ids that components/field.html renders.
    """
    attrs = {}
    # The prototype's inputs have no placeholder text; the label says it all.
    field.field.widget.attrs.pop("placeholder", None)
    css = _widget_class(field)
    existing = field.field.widget.attrs.get("class", "")
    if css or existing:
        attrs["class"] = f"{existing} {css}".strip()
    described = []
    if field.help_text:
        described.append(f"{field.auto_id}-hint")
    if field.errors:
        attrs["aria-invalid"] = "true"
        described.append(f"{field.auto_id}-err")
    if described:
        attrs["aria-describedby"] = " ".join(described)
    return field.as_widget(attrs=attrs)


@register.filter
def is_checkbox(field):
    return type(field.field.widget).__name__ == "CheckboxInput"


@register.filter
def is_password(field):
    return getattr(field.field.widget, "input_type", "") == "password"


@register.filter
def letter(index):
    """0 -> A, 1 -> B ...: the label beside an option (its screen position, nothing more)."""
    try:
        return "ABCDEF"[int(index)]
    except (TypeError, ValueError, IndexError):
        return ""


@register.filter
def elapsed_seconds(since):
    """Whole seconds from `since` until now (the count-up timer starts from this)."""
    return max(0, int((timezone.now() - since).total_seconds()))


@register.simple_tag
def engine_labels():
    """The interactive engine's labels in the page language, as a json_script element (Stage 8)."""
    from django.utils.html import json_script

    from apps.questions.engine_labels import engine_labels as labels

    return json_script(labels(), "engine-labels")

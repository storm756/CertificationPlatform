"""The question editor form: a schema-driven django-jsonform editor for the question body.

The editor's schema comes from the same pydantic model that validates the body on save
(`apps.questions.schemas.SCHEMAS`), so there is one definition of a valid question. The form
reuses `schemas.parse_body` for its errors; `services.add_version` validates again when saving.
"""

from copy import deepcopy

from django import forms
from django.utils.translation import gettext_lazy as _
from django_jsonform.forms.fields import JSONFormField
from pydantic import ValidationError

from apps.questions import schemas
from apps.questions.models import Pool


def _resolve(node, defs):
    """Inline $ref, fold "X or null" into X, and drop keywords the editor does not use."""
    if isinstance(node, list):
        return [_resolve(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _resolve(deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]), defs)
    if "anyOf" in node:
        options = [o for o in node["anyOf"] if o.get("type") != "null"]
        merged = {k: v for k, v in node.items() if k != "anyOf"}
        if len(options) == 1:
            return _resolve({**options[0], **merged}, defs)
        return _resolve({**options[0], **merged}, defs) if options else merged
    out = {
        k: _resolve(v, defs)
        for k, v in node.items()
        # "title" is pydantic's label when its value is text; a property can also be CALLED title
        if k not in ("additionalProperties", "$defs") and not (k == "title" and isinstance(v, str))
    }
    extra = node.get("additionalProperties")
    if node.get("type") == "object" and "properties" not in node and isinstance(extra, dict):
        # a dictionary with free keys (e.g. an MCQ gate reasons): empty "keys", values from additionalProperties
        out["keys"] = {}
        out["additionalProperties"] = _resolve(extra, defs)
    return out


def form_schema(fmt: str) -> dict:
    """The editor schema for one question format, built from its pydantic model."""
    raw = schemas.SCHEMAS[fmt].model_json_schema()
    return _resolve(raw, raw.get("$defs", {}))


def _optional_paths(node, defs, path=()):
    """Names of properties that are optional-or-null in the model: empty editor values for these
    are dropped before validation instead of being saved as "" or null."""
    out = set()
    if isinstance(node, dict):
        if "$ref" in node:
            return _optional_paths(defs[node["$ref"].rsplit("/", 1)[-1]], defs, path)
        for name, sub in node.get("properties", {}).items():
            if any(o.get("type") == "null" for o in sub.get("anyOf", [])):
                out.add(name)
            out |= _optional_paths(sub, defs, path)
        if "items" in node:
            out |= _optional_paths(node["items"], defs, path)
    return out


def strip_empty(fmt: str, body):
    """Drop "" and null for properties the model allows to be absent."""
    raw = schemas.SCHEMAS[fmt].model_json_schema()
    optional = _optional_paths(raw, raw.get("$defs", {}))

    def walk(node):
        if isinstance(node, dict):
            return {
                k: walk(v)
                for k, v in node.items()
                if not (k in optional and (v is None or v == "" or v == []))
            }
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(body)


class BodyField(JSONFormField):
    """The schema editor field. django-jsonform also validates the data against the schema on the
    server, more strictly than our pydantic models (it rejects null for an optional field and
    wants every key present). The pydantic models are the one authority, so only they validate."""

    def validate(self, value):
        forms.JSONField.validate(self, value)


class QuestionForm(forms.Form):
    """Body (schema editor), tags and pool for one question."""

    pc = forms.CharField(label=_("PC tag"), required=False)
    type = forms.CharField(label=_("Type"), required=False)
    pool = forms.ChoiceField(label=_("Pool"))
    keep_live = forms.BooleanField(
        label=_("Keep it live (publishes this version now)"), required=False
    )

    def __init__(self, *args, question, version, pools, is_admin, **kwargs):
        super().__init__(*args, **kwargs)
        self.question = question
        self.fields = {
            "body": BodyField(
                schema=form_schema(question.format),
                label=_("Question"),
                initial=version.body if version else {},
            ),
            **self.fields,
        }
        self.fields["pool"].choices = [(p, dict(Pool.choices)[p]) for p in pools]
        if not is_admin:
            del self.fields["keep_live"]

    def clean_body(self):
        body = self.cleaned_data["body"]
        if not isinstance(body, dict):
            raise forms.ValidationError(_("The question must be an object."))
        body = strip_empty(self.question.format, body)
        try:
            schemas.parse_body(self.question.format, body)
        except ValidationError as exc:
            raise forms.ValidationError(
                [
                    f"{'.'.join(str(p) for p in e['loc']) or 'body'}: {e['msg']}"
                    for e in exc.errors()
                ]
            ) from None
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from None
        return body

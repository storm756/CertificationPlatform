"""Legacy lesson content → modules, units and published versions (docs/legacy-sources.md).

Sources (private, in content-data/legacy/lessons/, never in git):
* booklet_text.json: the reading topics, {module: {index: {title, blocks}}} (55 topics).
* modules.php: each module's overview (pages 1–3 of the module PDFs), a PHP array.
* modules_ext.json: pages 4–8 (four steps, situation cards, guided lab, role-plays, worksheet).
* videos/m<N>.json and m<N>.jpg: film transcripts and posters. In the JSON the keys are swapped:
  `zh` holds the English line and `en` the Hindi one.

Every reading topic gets at least one inline interaction (the HOD's ask): the module's situation
cards become "predict, then reveal" prompts, its protection pairs become flip cards and its
"ask yourself" questions become a reflection list. Each one goes to the topic whose words it
shares most. The three myths per module become the module's "Myth or fact" practice check.
Jumbled tables are imported as they are and flagged "being fixed".

The importer is create-only. It refuses to run once any unit has been edited in the app.
"""

import json
import math
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from . import media, services
from .blocks import has_interaction, validate_blocks, validate_overview
from .models import MediaKind, Module, Unit, UnitType, UnitVersion, VersionSource

# Tables the content team named as jumbled (module, table number within the module, from 0).
NAMED_JUMBLED = {(1, 0), (1, 4), (2, 3), (4, 0), (4, 3)}
WORDS_PER_MINUTE = 150


class ImportRefused(Exception):
    pass


# --- a small reader for the PHP array file ------------------------------------------------------


_TOKEN = re.compile(
    r"""\s*(?:
        (?P<comment>//[^\n]*|\#[^\n]*|/\*.*?\*/)
      | (?P<sq>'(?:[^'\\]|\\.)*')
      | (?P<dq>"(?:[^"\\]|\\.)*")
      | (?P<num>-?\d+(?:\.\d+)?)
      | (?P<arrow>=>)
      | (?P<punct>[\[\],;])
      | (?P<word>[A-Za-z_]+)
    )""",
    re.S | re.X,
)


def _tokens(text):
    pos, end = 0, len(text)
    while pos < end:
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                return
            raise ValueError(f"PHP parse error near: {text[pos : pos + 40]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "comment":
            continue
        yield kind, m.group(kind)


def parse_php_array(text: str):
    """The value after `return` in a PHP file made of arrays, strings, numbers and booleans."""
    start = text.index("return")
    tokens = list(_tokens(text[start + len("return") :]))
    pos = 0

    def value():
        nonlocal pos
        kind, tok = tokens[pos]
        pos += 1
        if kind == "sq":
            return re.sub(r"\\([\\'])", r"\1", tok[1:-1])
        if kind == "dq":
            return json.loads(tok)
        if kind == "num":
            return Decimal(tok) if "." in tok else int(tok)
        if kind == "word":
            return {"true": True, "false": False, "null": None}[tok.lower()]
        if tok == "[":
            items, keyed = [], False
            while tokens[pos][1] != "]":
                first = value()
                if tokens[pos][0] == "arrow":
                    pos += 1
                    items.append((first, value()))
                    keyed = True
                else:
                    items.append((None, first))
                if tokens[pos][1] == ",":
                    pos += 1
            pos += 1
            return dict(items) if keyed else [v for _, v in items]
        raise ValueError(f"unexpected {tok!r}")

    return value()


# --- conversion ----------------------------------------------------------------------------------


def _para(text):
    return {"type": "paragraph", "spans": [{"text": text}]}


def _looks_jumbled(rows) -> bool:
    for row in rows:
        for cell in row:
            if "   " in cell:
                return True
        first = row[0].strip() if row else ""
        if first and (first[0].islower() or first[0] in ")”"):
            return True
    return False


def booklet_blocks(raw_blocks, module_no, table_counter) -> list[dict]:
    out = []
    for b in raw_blocks:
        kind = b["type"]
        if kind == "h":
            out.append({"type": "heading", "text": b["text"], "level": 2})
        elif kind == "p":
            out.append(_para(b["text"]))
        elif kind == "ul":
            out.append({"type": "list", "items": b["items"]})
        elif kind in ("kv", "cols"):
            n = table_counter[module_no]
            table_counter[module_no] += 1
            rows = [list(r) for r in b.get("rows", [])]
            head = list(b.get("head") or [])
            fixed = (module_no, n) in NAMED_JUMBLED or _looks_jumbled(
                rows + ([head] if head else [])
            )
            if kind == "kv" and not fixed and all(len(r) == 2 for r in rows):
                out.append({"type": "pairs", "rows": rows})
            else:
                out.append({"type": "table", "head": head, "rows": rows, "being_fixed": fixed})
        elif kind in ("case", "remember"):
            inner = [
                x
                for x in booklet_blocks(b.get("blocks", []), module_no, table_counter)
                if x["type"] in ("paragraph", "list")
            ]
            if inner:
                out.append({"type": kind, "blocks": inner})
        elif kind == "ssr":
            out.append({"type": "stop_save_report", "stop": [b.get("stop", "")], "save": [b.get("save", "")], "report": [b.get("report", "")]})  # fmt: skip
    for b in out:
        if b["type"] == "stop_save_report":
            for key in ("stop", "save", "report"):
                b[key] = [x for x in b[key] if x]
    return out


def _words(text: str) -> Counter:
    stop = {"the", "and", "a", "an", "to", "of", "in", "on", "for", "or", "is", "it", "your", "you", "with", "that", "this", "are", "be", "by", "as", "at", "from", "not", "can", "if", "their", "they", "them", "do", "what", "how", "who", "when", "will", "has", "have", "was", "but", "all", "any", "one"}  # fmt: skip
    return Counter(
        w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in stop
    )


def _block_text(blocks) -> str:
    parts = []
    for b in blocks:
        parts += [str(v) for k, v in b.items() if isinstance(v, str)]
        for key in ("items", "rows", "spans", "blocks", "head"):
            if key in b:
                parts.append(json.dumps(b[key], ensure_ascii=False))
    return " ".join(parts)


def interactions_for(module_no, overview_php, ext) -> list[tuple[str, dict]]:
    """(matching text, block) candidates for the module's reading topics."""
    found = []
    for card in (ext.get("cards") or {}).get("cards", []):
        prompt = f"{card['h']}. {card.get('k1', 'Signal')}: {card['v1']} What would you do?"
        answer = f"{card.get('k2', 'Response')}: {card['v2']}"
        found.append((prompt + " " + answer, {"type": "reveal", "label": "Predict, then reveal", "prompt": prompt, "answer": answer}))  # fmt: skip
    for front, back in overview_php.get("protect") or []:
        found.append((front + " " + back, {"type": "flipcards", "heading": "Flip the card: how to protect yourself", "cards": [{"front": front, "back": back}]}))  # fmt: skip
    for question in overview_php.get("ask") or []:
        found.append((question, {"type": "ask_yourself", "items": [question]}))
    return found


def place_interactions(topics: list[list[dict]], candidates) -> list[list[dict]]:
    """Give each candidate to the topic it shares most words with, make sure every topic gets one,
    merge flip cards and questions per topic, and insert them between the topic's sections."""
    vocab = [_words(_block_text(t)) for t in topics]
    chosen = [[] for _ in topics]
    for text, block in candidates:
        words = _words(text)
        scores = [sum(min(words[w], v[w]) for w in words) for v in vocab]
        best = max(range(len(topics)), key=lambda i: (scores[i], -len(chosen[i])))
        chosen[best].append((scores[best], block))
    # every topic gets at least one: take the weakest match from a topic that has more than one
    for i in range(len(topics)):
        while not chosen[i]:
            donor = max(range(len(topics)), key=lambda j: len(chosen[j]))
            if len(chosen[donor]) <= 1:
                break
            chosen[donor].sort(key=lambda sb: sb[0])
            chosen[i].append(chosen[donor].pop(0))
    result = []
    for topic, picks in zip(topics, chosen, strict=True):
        merged, flips, asks = [], [], []
        for _, block in picks:
            if block["type"] == "flipcards":
                flips += block["cards"]
            elif block["type"] == "ask_yourself":
                asks += block["items"]
            else:
                merged.append(block)
        if flips:
            merged.append({"type": "flipcards", "heading": "Flip the card: how to protect yourself", "cards": flips[:12]})  # fmt: skip
        if asks:
            merged.append({"type": "ask_yourself", "items": asks[:20]})
        headings = [i for i, b in enumerate(topic) if b["type"] == "heading"]
        at = (
            headings[len(headings) // 2]
            if len(headings) >= 2
            else next(
                (i for i, b in enumerate(topic) if b["type"] in ("stop_save_report", "remember")),
                len(topic),
            )
        )
        result.append(topic[:at] + merged + topic[at:])
    return result


def _minutes(blocks) -> int:
    return max(5, math.ceil(len(_block_text(blocks).split()) / WORDS_PER_MINUTE))


def handout_blocks(o: dict, e: dict) -> list[dict]:
    out = []
    add = out.append
    if o.get("what"):
        add({"type": "heading", "text": "What is it?", "level": 2})
        add(_para(o["what"]))
    if o.get("meet"):
        add({"type": "cards", "heading": o["meet"][0], "cards": [{"title": a, "text": b} for a, b in o["meet"][1]]})  # fmt: skip
    if o.get("how"):
        add({"type": "heading", "text": o.get("howh") or "How it works", "level": 2})
        add({"type": "cards", "cards": [{"title": a, "text": b} for a, b in o["how"]]})
    for b in o.get("blocks") or []:
        kind, heading = b[0], b[1]
        if kind == "signs":
            add({"type": "signs", "heading": heading, "items": [x.strip() for x in str(b[2]).split(" · ") if x.strip()]})  # fmt: skip
        elif kind == "cards":
            add({"type": "cards", "heading": heading, "cards": [{"title": a, "text": c} for a, c in b[2]]})  # fmt: skip
        elif kind == "list":
            add({"type": "heading", "text": heading, "level": 3})
            add(
                {
                    "type": "list",
                    "items": list(b[2]),
                    "ordered": bool(b[3]) if len(b) > 3 else False,
                }
            )
        elif kind == "table":
            add({"type": "table", "caption": heading, "head": list(b[2]), "rows": [list(r) for r in b[3]]})  # fmt: skip
        elif kind == "urgency":
            add({"type": "urgency", "heading": heading, "rows": [dict(zip(("colour", "label", "level", "when", "action", "time"), r, strict=True)) for r in b[2]]})  # fmt: skip
    if o.get("callout"):
        add({"type": "callout", "tone": "key", "label": "Key rule", "text": o["callout"]})
    if o.get("stop") or o.get("save") or o.get("report"):
        add({"type": "heading", "text": o.get("stepsh") or "Stop · Save · Report", "level": 2})
        add({"type": "stop_save_report", "stop": o.get("stop") or [], "save": o.get("save") or [], "report": o.get("report") or []})  # fmt: skip
    if o.get("protect"):
        add({"type": "heading", "text": "How to protect yourself and others", "level": 2})
        add({"type": "cards", "cards": [{"title": a, "text": b} for a, b in o["protect"]]})
    if o.get("rules"):
        add({"type": "heading", "text": "Golden rules", "level": 3})
        add({"type": "list", "items": list(o["rules"]), "ordered": True})
    if o.get("ask"):
        add({"type": "ask_yourself", "items": list(o["ask"])})
    if o.get("remember"):
        add({"type": "remember", "blocks": [{"type": "list", "items": list(o["remember"])}]})
    if o.get("story"):
        add({"type": "callout", "tone": "case", "label": "Real-life lesson", "text": o["story"]})
    s = e.get("steps")
    if s:
        add({"type": "heading", "text": s["title"], "level": 2})
        add(_para(s["intro"]))
        add({"type": "list", "ordered": True, "items": [f"{x['h']}. {x['p']}" for x in s["steps"]]})
        if s.get("check"):
            add({"type": "callout", "tone": "ask", "label": "Think aloud", "text": s["check"]})
    c = e.get("cards")
    if c:
        add({"type": "heading", "text": c["title"], "level": 2})
        add(_para(c["intro"]))
        add({"type": "cards", "cards": [{"title": x["h"], "text": f"{x['k1']}: {x['v1']} {x['k2']}: {x['v2']}"} for x in c["cards"]]})  # fmt: skip
        if c.get("think"):
            add({"type": "callout", "tone": "key", "label": c.get("thinkk") or "Decision test", "text": c["think"]})  # fmt: skip
    lab = e.get("lab")
    if lab:
        add({"type": "heading", "text": lab["title"], "level": 2})
        add(_para(lab["intro"]))
        add({"type": "cards", "cards": [{"label": x.get("k", ""), "title": x["h"], "text": x["p"]} for x in lab["stations"]]})  # fmt: skip
        if lab.get("expect"):
            add({"type": "callout", "tone": "remember", "label": "What good looks like", "text": lab["expect"]})  # fmt: skip
    cs = e.get("cases")
    if cs:
        add({"type": "heading", "text": cs["title"], "level": 2})
        add(_para(cs["intro"]))
        add({"type": "cards", "cards": [{"label": x.get("k", ""), "title": x["h"], "text": x["p"]} for x in cs["cases"]]})  # fmt: skip
        if cs.get("rubric"):
            add({"type": "heading", "text": "Observer checklist", "level": 3})
            add({"type": "list", "items": list(cs["rubric"])})
        if cs.get("discuss"):
            add({"type": "callout", "tone": "ask", "label": "Discuss", "text": cs["discuss"]})
    sh = e.get("sheet")
    if sh:
        add({"type": "heading", "text": sh["title"], "level": 2})
        add(_para(sh["intro"]))
        add({"type": "list", "ordered": True, "items": list(sh["questions"])})
        if sh.get("script"):
            add({"type": "callout", "tone": "remember", "label": sh.get("scripth") or "Script", "text": sh["script"]})  # fmt: skip
        if sh.get("selfcheck"):
            add({"type": "callout", "tone": "case", "label": "Self-check", "text": sh["selfcheck"]})
    return out


def video_blocks(transcript: dict, poster_id) -> list[dict]:
    lines = [
        {"t0": float(x["t0"]), "t1": float(x["t1"]), "en": x.get("zh", ""), "hi": x.get("en", "")}
        for x in transcript.get("lines", [])
    ]  # the legacy keys are swapped: zh = English, en = Hindi
    return [{"type": "video", "youtube_id": "", "poster": poster_id, "duration": float(transcript.get("dur") or 0), "transcript": lines}]  # fmt: skip


# --- the run ------------------------------------------------------------------------------------


def load_sources(source: Path) -> dict:
    php = parse_php_array((source / "modules.php").read_text("utf-8"))
    return {
        "booklet": json.loads((source / "booklet_text.json").read_text("utf-8")),
        "modules": {int(k): v for k, v in php.items()},
        "ext": {
            int(k): v
            for k, v in json.loads((source / "modules_ext.json").read_text("utf-8")).items()
        },  # fmt: skip
        "videos": source / "videos",
        "handouts": source / "handouts",
    }


def plan(sources: dict) -> dict:
    """Everything the import would create, validated, without touching the database."""
    modules = {}
    table_counter = Counter()
    for n in sorted(int(k) for k in sources["booklet"]):
        topics_raw = sources["booklet"][str(n)]
        o, e = sources["modules"].get(n, {}), sources["ext"].get(n, {})
        topics = [booklet_blocks(topics_raw[k]["blocks"], n, table_counter) for k in sorted(topics_raw, key=int)]  # fmt: skip
        topics = place_interactions(topics, interactions_for(n, o, e))
        titles = [topics_raw[k]["title"] for k in sorted(topics_raw, key=int)]
        myths = [{"type": "mythfact", "statement": s, "is_fact": bool(f), "why": w} for s, f, w in o.get("myths") or []]  # fmt: skip
        transcript_file = sources["videos"] / f"m{n}.json"
        modules[n] = {
            "title": o.get("title", ""),
            "tagline": o.get("tagline", ""),
            "theory": o.get("theory"),
            "practical": o.get("practical"),
            "overview": validate_overview(
                {
                    k: o.get(k) or ([] if k in ("outcomes", "stop", "save", "report") else "")
                    for k in ("what", "outcomes", "callout", "stop", "save", "report")
                }
            ),  # fmt: skip
            "topics": [(t, validate_blocks(b)) for t, b in zip(titles, topics, strict=True)],
            "handout": validate_blocks(handout_blocks(o, e)),
            "check": validate_blocks(
                [
                    _para(
                        "Three quick statements from this module. Decide whether each is a myth or a fact, then see the explanation. This is practice: nothing is scored."
                    )
                ]
                + myths
            )
            if myths
            else None,  # fmt: skip
            "transcript": json.loads(transcript_file.read_text("utf-8"))
            if transcript_file.exists()
            else None,  # fmt: skip
            "poster": sources["videos"] / f"m{n}.jpg",
            "handout_pdf": sources["handouts"] / f"m{n}.pdf",
        }
    return modules


def report(planned: dict) -> dict:
    topics = sum(len(m["topics"]) for m in planned.values())
    return {
        "modules": len(planned),
        "reading_topics": topics,
        "topics_with_interaction": sum(
            1 for m in planned.values() for _, b in m["topics"] if has_interaction(b)
        ),  # fmt: skip
        "tables_being_fixed": sum(
            1 for m in planned.values() for _, b in m["topics"] for x in b if x.get("being_fixed")
        ),  # fmt: skip
        "films_with_transcript": sum(1 for m in planned.values() if m["transcript"]),
        "film_posters": sum(1 for m in planned.values() if m["poster"].exists()),
        "handout_pdfs": sum(1 for m in planned.values() if m["handout_pdf"].exists()),
        "youtube_ids": 0,
        "practice_checks": sum(1 for m in planned.values() if m["check"]),
    }


def _refuse_if_edited():
    edited = UnitVersion.objects.exclude(source=VersionSource.LEGACY).exists() or UnitVersion.objects.filter(version__gt=1).exists()  # fmt: skip
    if edited:
        raise ImportRefused(
            "Content has been edited in the app since the import. Not running again."
        )
    return Unit.objects.filter(module__number__lte=9).exists()


@transaction.atomic
def run(source: Path) -> dict:
    if _refuse_if_edited():
        return {"created": 0, "already_imported": True}
    planned = plan(load_sources(source))
    created = 0
    for n, m in planned.items():
        module = Module.objects.get(number=n)
        module.title, module.tagline = m["title"], m["tagline"]
        if m["theory"] is not None:
            module.theory_hours, module.practical_hours = m["theory"], m["practical"]
            module.hours = Decimal(str(m["theory"])) + Decimal(str(m["practical"]))
        module.overview = m["overview"]
        module.save()

        def unit(slug, kind, order, title, blocks, minutes, module=module):
            nonlocal created
            u = Unit.objects.create(module=module, slug=slug, type=kind, order=order, nominal_minutes=minutes)  # fmt: skip
            v = services.add_version(u, title, blocks, source=VersionSource.LEGACY)
            services.publish(v, None, system=True)
            created += 1

        poster = None
        if m["poster"].exists():
            poster = media.store(SimpleUploadedFile("poster.jpg", m["poster"].read_bytes()), module, MediaKind.POSTER, title=f"Module {n} film poster").pk  # fmt: skip
        if m["transcript"]:
            duration = float(m["transcript"].get("dur") or 0)
            unit("film", UnitType.VIDEO, 1, f"Film: {m['tagline'] or m['title']}", video_blocks(m["transcript"], poster), max(1, math.ceil(duration / 60)))  # fmt: skip
        for i, (title, blocks) in enumerate(m["topics"], start=1):
            unit(f"t{i}", UnitType.READING, 10 + i, title, blocks, _minutes(blocks))
        handout = list(m["handout"])
        if m["handout_pdf"].exists():
            pdf = media.store(SimpleUploadedFile("handout.pdf", m["handout_pdf"].read_bytes()), module, MediaKind.PDF, title=f"Module {n} handout")  # fmt: skip
            handout.insert(
                0, {"type": "attachment", "asset": pdf.pk, "label": f"Module {n} handout (PDF)"}
            )
        unit("handout", UnitType.HANDOUT, 50, f"Module {n} handout", handout, 20)
        if m["check"]:
            unit("check", UnitType.CHECK, 60, "Myth or fact", m["check"], 5)
    return {**report(planned), "created": created, "already_imported": False}

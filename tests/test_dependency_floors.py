"""Security floors for dependencies (security audit 2026-11, H2).

Pillow decodes uploaded pictures (lesson images, posters, hotspot art, Word-file images), so a
decoder bug is reachable from an upload. 12.0.0 had 61 published advisories (pip-audit); 13.0.0
fixes them all. If a pin ever goes below a floor, this fails before the image is built.
"""

from importlib.metadata import version


def _tuple(text):
    return tuple(int(part) for part in text.split(".")[:3])


def test_pillow_is_at_least_the_patched_release():
    assert _tuple(version("Pillow")) >= (13, 0, 0)

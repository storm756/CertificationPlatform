"""Stage 10: the edge Caddy is changed only by `deploy.sh edge`, never by a staging or prod deploy."""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def _env_part(script: str) -> str:
    """Everything deploy.sh runs for staging|prod (after the `case` that sends edge elsewhere)."""
    return script.split("esac", 1)[1]


def test_env_deploys_never_touch_caddy():
    env_part = _env_part((DEPLOY / "deploy.sh").read_text(encoding="utf-8"))
    for forbidden in ("compose.edge.yml", "caddy reload", "caddy validate", "/etc/caddy"):
        assert forbidden not in env_part, forbidden


def test_edge_is_its_own_step():
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert re.search(r'edge\) shift; exec "\$\(dirname "\$0"\)/edge\.sh" "\$@"', script)


def test_edge_validates_before_installing_and_rolls_back():
    edge = (DEPLOY / "edge.sh").read_text(encoding="utf-8")
    assert 'REF="${1:-main}"' in edge
    assert 'EDGE="$ROOT/edge"' in edge
    validate, install, reload = (
        edge.index("caddy validate"),
        edge.index('cat "$NEW" > "$LIVE"'),
        edge.index("reload --config"),
    )
    assert validate < install < reload
    assert "Caddyfile.prev" in edge[reload:]  # a failed reload puts the previous file back


def test_edge_compose_mounts_its_own_directory():
    compose = (DEPLOY / "compose.edge.yml").read_text(encoding="utf-8")
    assert "name: csfr-edge" in compose  # same project name: the TLS certificate volume is kept
    assert "- ./caddy:/etc/caddy:ro" in compose

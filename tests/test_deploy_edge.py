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


# --- the staging login (security audit 2026-11) --------------------------------------------------


def _site(caddyfile: str, name: str) -> str:
    start = caddyfile.index("{$SCHEME}{$" + name + "} {")
    return caddyfile[start : caddyfile.index("\n}\n", start)]


def test_staging_is_behind_a_login_but_healthz_and_prod_are_not():
    caddyfile = (DEPLOY / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    staging, prod = _site(caddyfile, "STAGING_DOMAIN"), _site(caddyfile, "PROD_DOMAIN")
    assert "@team not path /healthz/" in staging
    assert "basic_auth @team" in staging and "{$STAGING_AUTH_HASH}" in staging
    assert "basic_auth" not in prod


def test_the_login_comes_from_the_server_never_from_git():
    caddyfile = (DEPLOY / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "$2a$" not in caddyfile and "$2b$" not in caddyfile  # no bcrypt hash committed
    compose = (DEPLOY / "compose.edge.yml").read_text(encoding="utf-8")
    assert "STAGING_AUTH_HASH: ${STAGING_AUTH_HASH:-}" in compose


def test_www_redirects_to_an_absolute_url_on_the_apex():
    # 17 Nov 2026: `redir {$SCHEME}{$PROD_DOMAIN}{uri}` became the relative path "cyberfirstresponse.io/" on
    # the server (SCHEME is empty there), so https://www.cyberfirstresponse.io/ redirected to itself forever.
    caddyfile = (DEPLOY / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    start = caddyfile.index("{$SCHEME}www.{$PROD_DOMAIN} {")
    www = caddyfile[start : caddyfile.index("\n}\n", start)]
    assert "redir {scheme}://{$PROD_DOMAIN}{uri} permanent" in www
    # Never a scheme from the environment: it may be empty, which makes a relative target.
    assert not re.search(r"redir\s+\{\$SCHEME\}", caddyfile)
    assert "header -Server" in www


def test_edge_refuses_to_install_without_the_login():
    edge = (DEPLOY / "edge.sh").read_text(encoding="utf-8")
    check = edge.index('[ -z "${STAGING_AUTH_HASH:-}" ]')
    assert check < edge.index("caddy validate") < edge.index('cat "$NEW" > "$LIVE"')
    assert '-e STAGING_AUTH_HASH="$STAGING_AUTH_HASH"' in edge  # the validation sees it too

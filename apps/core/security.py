"""Security headers for every Django response (architecture §16, Stage 10).

One strict Content-Security-Policy for the site: our own files only, plus the youtube-nocookie
frame for films. YouTube's player script (www.youtube.com/iframe_api) is allowed only on a lesson
page that really shows a YouTube film (`allow_youtube_script`). The admin and Rosetta (staff only,
behind 2FA) need inline scripts and styles from django-unfold, so they get a separate policy that is
still limited to our own origin.

Caddy adds the same strict policy only to responses that have none (the files it serves itself).
"""

YOUTUBE_FRAME = "https://www.youtube-nocookie.com"
YOUTUBE_SCRIPT = "https://www.youtube.com"

STRICT = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'"],
    "media-src": ["'self'"],
    "connect-src": ["'self'"],
    "frame-src": [YOUTUBE_FRAME],
    "object-src": ["'none'"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
}

STAFF_TOOLS = {
    **STRICT,
    "script-src": ["'self'", "'unsafe-inline'", "'unsafe-eval'"],  # unfold: Alpine.js, inline JS
    "style-src": ["'self'", "'unsafe-inline'"],
    "frame-src": ["'self'"],
}
STAFF_TOOL_PREFIXES = ("/admin/", "/rosetta/")

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


def render(policy: dict[str, list[str]]) -> str:
    return "; ".join(f"{name} {' '.join(values)}" for name, values in policy.items())


def allow_youtube_script(request) -> None:
    """Call from a view whose page embeds a YouTube film, so the IFrame API may load."""
    request.csp_youtube = True


def policy_for(request) -> dict[str, list[str]]:
    if request.path.startswith(STAFF_TOOL_PREFIXES):
        return STAFF_TOOLS
    if getattr(request, "csp_youtube", False):
        return {**STRICT, "script-src": ["'self'", YOUTUBE_SCRIPT]}
    return STRICT


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = render(policy_for(request))
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        return response

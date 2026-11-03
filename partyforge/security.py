import hmac
import html
import re
import secrets
from html.parser import HTMLParser
from urllib.parse import urlsplit
from functools import wraps

import bleach
from flask import abort, redirect, request, session, url_for

ALLOWED_TAGS = [
    "div",
    "span",
    "p",
    "h2",
    "h3",
    "strong",
    "em",
    "small",
    "ul",
    "ol",
    "li",
    "br",
    "hr",
]
ALLOWED_ATTRIBUTES = {
    "*": ["class", "aria-hidden", "role"],
}
CSS_DENYLIST = (
    "</style",
    "<script",
    "javascript:",
    "expression(",
    "@import",
    "url(",
    "behavior:",
    "-moz-binding",
)
DESCRIPTION_TAGS = [
    "p",
    "br",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "h2",
    "h3",
    "blockquote",
    "a",
]
DESCRIPTION_ATTRIBUTES = {"a": ["href", "title"]}


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


def verify_csrf():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("_csrf", "")
        supplied = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, "Invalid or missing form token.")
    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin") or not session.get("host_user_id"):
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def current_host():
    from . import db
    from .models import HostUser

    return db.session.get(HostUser, session.get("host_user_id"))


def event_for_host(event_id, owner_only=False):
    from .models import Event, EventHost

    user = current_host()
    if not user or not user.active:
        abort(403)
    query = Event.query.join(EventHost).filter(
        Event.id == event_id, EventHost.user_id == user.id
    )
    if owner_only:
        query = query.filter(EventHost.role == "owner")
    return query.first_or_404()


def clean_html(value):
    return bleach.clean(
        (value or "")[:20000],
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )


def description_html(value):
    """Render old rich-text descriptions and new plain text safely."""
    decoded = html.unescape(value or "")
    cleaned = bleach.clean(
        decoded,
        tags=DESCRIPTION_TAGS,
        attributes=DESCRIPTION_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return cleaned.replace("\r\n", "\n").replace("\n", "<br>")


def description_content(value):
    """Only trusted TikTok video URLs become application-owned players.

    User HTML still cannot supply iframes or scripts. No URL is fetched by
    the server, and private invitation URLs are never sent as referrers.
    """
    class VideoLinks(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.output = []
            self.videos = []
            self.in_video_link = False

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                href = dict(attrs).get("href", "")
                try:
                    url = urlsplit(href)
                    match = re.fullmatch(r"/@[\w.-]+/video/(\d{10,25})/?", url.path)
                    trusted = url.scheme in {"https", "http"} and url.hostname in {"www.tiktok.com", "tiktok.com"} and not url.username and not url.password and url.port in {None, 443, 80}
                except ValueError:
                    match, trusted = None, False
                if match and trusted:
                    video_id = match.group(1)
                    existing = next((v for v in self.videos if v["id"] == video_id), None)
                    if not existing:
                        existing = {"id": video_id, "url": "https://www.tiktok.com" + url.path.rstrip("/"), "number": len(self.videos) + 1}
                        self.videos.append(existing)
                    self.output.append(f'<a class="video-reference" href="#video-{video_id}">TikTok video {existing["number"]} ↓</a>')
                    self.in_video_link = True
                    return
            if not self.in_video_link:
                self.output.append(self.get_starttag_text())

        def handle_endtag(self, tag):
            if tag == "a" and self.in_video_link:
                self.in_video_link = False
            elif not self.in_video_link:
                self.output.append(f"</{tag}>")

        def handle_data(self, data):
            if not self.in_video_link:
                self.output.append(data)

        def handle_entityref(self, name):
            self.handle_data(f"&{name};")

        def handle_charref(self, name):
            self.handle_data(f"&#{name};")

    parser = VideoLinks()
    parser.feed(bleach.linkify(description_html(value), parse_email=False))
    return {"html": "".join(parser.output), "videos": parser.videos}


def clean_css(value):
    value = (value or "")[:40000]
    lowered = value.lower()
    if any(item in lowered for item in CSS_DENYLIST):
        raise ValueError(
            "CSS contains a blocked construct. Remote URLs, imports, scripts, and expressions are not allowed."
        )
    value = re.sub(r"</?style[^>]*>", "", value, flags=re.IGNORECASE)
    return value

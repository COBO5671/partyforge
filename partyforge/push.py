import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from flask import current_app
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from . import db
from .models import EventHost, Guest, PushSubscription

PUSH_CATEGORIES = {"event", "reminders", "rsvp", "potluck", "polls", "announcements"}


def ensure_vapid_keys():
    private_path = Path(current_app.config["VAPID_PRIVATE_KEY"])
    public_path = Path(current_app.config["VAPID_PUBLIC_KEY"])
    private_path.parent.mkdir(parents=True, exist_ok=True)
    if not private_path.exists():
        vapid = Vapid()
        vapid.generate_keys()
        vapid.save_key(str(private_path))
        raw = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        public_path.write_text(base64.urlsafe_b64encode(raw).rstrip(b"=").decode())
    elif not public_path.exists():
        vapid = Vapid.from_file(str(private_path))
        raw = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        public_path.write_text(base64.urlsafe_b64encode(raw).rstrip(b"=").decode())
    return public_path.read_text().strip()


def public_vapid_key():
    return ensure_vapid_keys()


def subscription_state(endpoint, guest=None, host_user=None):
    query = PushSubscription.query.filter_by(endpoint=endpoint)
    query = query.filter_by(guest_id=guest.id) if guest else query.filter_by(host_user_id=host_user.id)
    item = query.first()
    return {"subscribed": bool(item), "categories": sorted(item.categories) if item else []}


def save_subscription(subscription_info, categories, guest=None, host_user=None):
    if not isinstance(subscription_info, dict) or not isinstance(categories, list):
        raise ValueError("Invalid notification settings.")
    endpoint = str(subscription_info.get("endpoint", ""))[:4000]
    keys = subscription_info.get("keys") or {}
    if not isinstance(keys, dict) or not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("The browser did not provide a valid push subscription.")
    query = PushSubscription.query.filter_by(endpoint=endpoint)
    query = query.filter_by(guest_id=guest.id) if guest else query.filter_by(host_user_id=host_user.id)
    item = query.first()
    if not item:
        item = PushSubscription(endpoint=endpoint, guest=guest, host_user=host_user)
        db.session.add(item)
    item.keys_json = json.dumps({"p256dh": keys["p256dh"], "auth": keys["auth"]})
    item.categories_json = json.dumps(sorted({value for value in categories if isinstance(value, str)} & PUSH_CATEGORIES))
    return item


def remove_subscription(endpoint, guest=None, host_user=None):
    query = PushSubscription.query.filter_by(endpoint=endpoint)
    query = query.filter_by(guest_id=guest.id) if guest else query.filter_by(host_user_id=host_user.id)
    query.delete()


def _deliver(rows, title, body, url, tag):
    if not rows:
        return 0
    expired = []
    delivered = 0
    for item in rows:
        try:
            target_url = url(item) if callable(url) else url
            payload = json.dumps({"title": title, "body": body, "url": target_url, "tag": tag})
            webpush(
                subscription_info=item.subscription_info,
                data=payload,
                vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": current_app.config["VAPID_SUBJECT"]},
                ttl=86400,
            )
            delivered += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                expired.append(item)
            else:
                current_app.logger.warning("Web push failed: %s", exc)
        except Exception:
            current_app.logger.exception("Web push failed")
    for item in expired:
        db.session.delete(item)
    if expired:
        db.session.commit()
    return delivered


def send_guest_push(event, category, title, body, url, exclude_guest=None):
    rows = (
        PushSubscription.query.join(Guest, PushSubscription.guest_id == Guest.id)
        .filter(Guest.event_id == event.id)
        .all()
    )
    rows = [
        item
        for item in rows
        if category in item.categories
        and (not exclude_guest or item.guest_id != exclude_guest.id)
        and item.guest.status in {"yes", "maybe"}
    ]
    target = (lambda item: f"/i/{item.guest.token}") if url is None else url
    return _deliver(rows, title, body, target, f"event-{event.id}-{category}")


def send_host_push(event, category, title, body, url):
    host_ids = [link.user_id for link in EventHost.query.filter_by(event_id=event.id).all()]
    if not host_ids:
        return 0
    rows = PushSubscription.query.filter(PushSubscription.host_user_id.in_(host_ids)).all()
    rows = [item for item in rows if category in item.categories]
    return _deliver(rows, title, body, url, f"host-{event.id}-{category}")

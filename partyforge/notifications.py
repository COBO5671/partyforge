import smtplib
from email.message import EmailMessage

from flask import current_app, has_request_context, url_for

from . import db
from .models import EventActivity, Guest, GuestSubscription, Notification


def email_is_configured():
    return bool(current_app.config.get("SMTP_HOST") and current_app.config.get("MAIL_FROM"))


def _link(endpoint, **values):
    if has_request_context():
        return url_for(endpoint, _external=True, **values)
    base = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    relative = url_for(endpoint, _external=False, **values)
    return f"{base}{relative}" if base else relative


def _deliver(messages):
    if not messages or not email_is_configured():
        return False
    config = current_app.config
    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=10) as smtp:
            if config["SMTP_USE_TLS"]:
                smtp.starttls()
            if config.get("SMTP_USERNAME"):
                smtp.login(config["SMTP_USERNAME"], config.get("SMTP_PASSWORD", ""))
            for recipient, subject, body in messages:
                message = EmailMessage()
                message["From"] = config["MAIL_FROM"]
                message["To"] = recipient
                message["Subject"] = subject
                message.set_content(body)
                smtp.send_message(message)
        return True
    except Exception:
        current_app.logger.exception("PartyForge could not send notification email")
        return False


def host_notification(event, kind, title, message, actor=None):
    db.session.add(
        Notification(
            event=event,
            actor=actor,
            kind=kind,
            title=title[:180],
            message=message[:500],
        )
    )


def send_host_email(event, subject, message):
    addresses = {
        link.user.email.strip()
        for link in event.host_links
        if link.user and link.user.email and link.user.active
    }
    configured = current_app.config.get("HOST_EMAIL", "").strip()
    if configured:
        addresses.add(configured)
    if not addresses:
        return False
    event_url = _link("admin.manage_event", event_id=event.id)
    return _deliver([
        (address, f"{subject} · {event.title}", f"{message}\n\nManage event: {event_url}")
        for address in addresses
    ])


def guest_activity(event, kind, message, actor=None):
    db.session.add(
        EventActivity(event=event, actor=actor, kind=kind, message=message[:500])
    )


def send_subscriber_email(event, subject, message, exclude_guest=None):
    invitees = (
        Guest.query.join(GuestSubscription)
        .filter(
            Guest.event_id == event.id,
            GuestSubscription.all_updates.is_(True),
            Guest.email != "",
            Guest.status.in_(("yes", "maybe")),
        )
        .all()
    )
    messages = []
    for guest in invitees:
        if exclude_guest and guest.id == exclude_guest.id:
            continue
        invite_url = _link("public.invite", token=guest.token)
        messages.append(
            (
                guest.email,
                f"{subject} · {event.title}",
                f"Hi {guest.name},\n\n{message}\n\nOpen your event link: {invite_url}\n\nYou can turn these alerts off on your RSVP card.",
            )
        )
    return _deliver(messages)


def update_subscription(guest, enabled):
    subscription = guest.subscription
    if not subscription:
        subscription = GuestSubscription(guest=guest)
        db.session.add(subscription)
    subscription.all_updates = bool(enabled and guest.email)
    return subscription

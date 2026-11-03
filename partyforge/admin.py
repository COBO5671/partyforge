import csv
import io
import json
import uuid
from urllib.parse import urlsplit
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from . import db
from .event_time import event_now
from .models import (
    Event,
    EventBlock,
    EventHost,
    EventHighlight,
    EventSettings,
    Guest,
    HostUser,
    Notification,
    NotificationRead,
    Reminder,
)
from .notifications import email_is_configured, guest_activity, send_subscriber_email
from .push import send_guest_push
from .push import subscription_state, public_vapid_key, remove_subscription, save_subscription
from .security import admin_required, clean_css, clean_html, current_host, event_for_host

bp = Blueprint("admin", __name__, url_prefix="/admin")
ALLOWED_IMAGES = {"jpg", "jpeg", "png", "webp", "gif"}


def parse_datetime(value):
    return datetime.fromisoformat(value) if value else None


def save_banner(upload):
    if not upload or not upload.filename:
        return None
    filename = secure_filename(upload.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGES:
        raise ValueError("Banner must be JPG, PNG, WebP, or GIF.")
    stored = f"{uuid.uuid4().hex}.{extension}"
    upload.save(Path(current_app.config["UPLOAD_FOLDER"]) / stored)
    return stored


def populate_event(event):
    event.title = request.form.get("title", "").strip()[:160]
    event.subtitle = request.form.get("subtitle", "").strip()[:240]
    event.description = request.form.get("description", "").strip()[:10000]
    event.location = request.form.get("location", "").strip()[:300]
    event.start_at = parse_datetime(request.form.get("start_at"))
    event.end_at = parse_datetime(request.form.get("end_at"))
    event.timezone = request.form.get("timezone", "America/Chicago")[:64]
    event.allow_open_rsvp = request.form.get("allow_open_rsvp") == "on"
    event.show_guest_list = request.form.get("show_guest_list") == "on"
    if not event.settings:
        event.settings = EventSettings()
    event.settings.rsvp_deadline = parse_datetime(request.form.get("rsvp_deadline"))
    if "highlights_present" in request.form:
        event.highlights.clear()
        for index in range(3):
            title = request.form.get(f"highlight_title_{index}", "").strip()[:60]
            body = request.form.get(f"highlight_body_{index}", "").strip()[:240]
            if title and body:
                event.highlights.append(EventHighlight(title=title, body=body, position=index))
    if not event.title or not event.start_at:
        raise ValueError("Title and start time are required.")
    banner = save_banner(request.files.get("banner"))
    if banner:
        event.banner_filename = banner


@bp.get("")
@admin_required
def dashboard():
    user = current_host()
    events = (
        Event.query.join(EventHost)
        .filter(EventHost.user_id == user.id)
        .order_by(Event.start_at.desc())
        .all()
    )
    return render_template("dashboard.html", events=events)


@bp.route("/events/new", methods=["GET", "POST"])
@admin_required
def new_event():
    event = Event(
        start_at=datetime.now().replace(second=0, microsecond=0),
        show_guest_list=True,
    )
    if request.method == "POST":
        try:
            populate_event(event)
            db.session.add(event)
            db.session.flush()
            db.session.add(EventHost(event=event, user=current_host(), role="owner"))
            db.session.commit()
            flash("Event created. Add guests and party extras next.", "success")
            return redirect(url_for("admin.manage_event", event_id=event.id))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("event_form.html", event=event, is_new=True)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_event(event_id):
    event = event_for_host(event_id)
    if request.method == "POST":
        try:
            populate_event(event)
            guest_activity(event, "event", "The host updated the event details.")
            db.session.commit()
            send_subscriber_email(event, "Event details updated", "The host updated the event details. Open your invitation to see what changed.")
            send_guest_push(
                event,
                "event",
                f"{event.title} was updated",
                "The host updated the event details. Open your invitation to see what changed.",
                None,
            )
            flash("Event details saved.", "success")
            return redirect(url_for("admin.manage_event", event_id=event.id))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("event_form.html", event=event, is_new=False)


@bp.get("/events/<int:event_id>")
@admin_required
def manage_event(event_id):
    event = event_for_host(event_id)
    user = current_host()
    host_link = EventHost.query.filter_by(event_id=event.id, user_id=user.id).first()
    counts = {
        status: Guest.query.filter_by(event_id=event.id, status=status).count()
        for status in ("yes", "maybe", "no", "pending")
    }
    return render_template(
        "manage.html",
        event=event,
        counts=counts,
        email_configured=email_is_configured(),
        host_role=host_link.role,
        reminders=Reminder.query.filter_by(event_id=event.id).order_by(Reminder.send_at.desc()).all(),
    )


@bp.get("/notifications")
@admin_required
def notifications():
    event_ids = [link.event_id for link in current_host().event_links]
    items = (
        Notification.query.filter(Notification.event_id.in_(event_ids))
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    read_ids = {
        row.notification_id
        for row in NotificationRead.query.filter_by(host_user_id=current_host().id).all()
    }
    return render_template("notifications.html", notifications=items, read_ids=read_ids)


@bp.post("/notifications/read")
@admin_required
def mark_notifications_read():
    event_ids = [link.event_id for link in current_host().event_links]
    user = current_host()
    existing = {
        row.notification_id
        for row in NotificationRead.query.filter_by(host_user_id=user.id).all()
    }
    for item in Notification.query.filter(Notification.event_id.in_(event_ids)).all():
        if item.id not in existing:
            db.session.add(NotificationRead(notification=item, host_user_id=user.id))
    db.session.commit()
    return redirect(url_for("admin.notifications"))


@bp.post("/events/<int:event_id>/announce")
@admin_required
def announce(event_id):
    event = event_for_host(event_id)
    message = request.form.get("message", "").strip()[:500]
    if not message:
        flash("Write an announcement or reminder first.", "error")
        return redirect(url_for("admin.manage_event", event_id=event.id))
    guest_activity(event, "announcement", message)
    db.session.commit()
    sent = send_subscriber_email(event, "Message from the host", message)
    pushed = send_guest_push(
        event, "announcements", f"Update: {event.title}", message, None
    )
    flash(
        "Announcement posted" + (f" and pushed to {pushed} browser{'s' if pushed != 1 else ''}" if pushed else "") + ("; email was also sent." if sent else "."),
        "success",
    )
    return redirect(url_for("admin.manage_event", event_id=event.id))


@bp.post("/events/<int:event_id>/guests")
@admin_required
def add_guests(event_id):
    event = event_for_host(event_id)
    added = 0
    for raw_line in request.form.get("guest_lines", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        name = parts[0][:160]
        email = parts[1][:255] if len(parts) > 1 else ""
        try:
            limit = max(1, min(20, int(parts[2]))) if len(parts) > 2 else 1
        except ValueError:
            limit = 1
        if name:
            db.session.add(Guest(event=event, name=name, email=email, party_limit=limit))
            added += 1
    db.session.commit()
    flash(f"Added {added} guest{'s' if added != 1 else ''}.", "success")
    return redirect(url_for("admin.manage_event", event_id=event.id))


@bp.post("/events/<int:event_id>/guests/<int:guest_id>/delete")
@admin_required
def delete_guest(event_id, guest_id):
    event_for_host(event_id)
    guest = Guest.query.filter_by(id=guest_id, event_id=event_id).first_or_404()
    db.session.delete(guest)
    db.session.commit()
    flash("Guest removed.", "success")
    return redirect(url_for("admin.manage_event", event_id=event_id))


@bp.get("/events/<int:event_id>/guests.csv")
@admin_required
def export_guests(event_id):
    event = event_for_host(event_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Name", "Email", "Status", "Party size", "Party limit", "Dietary", "Note", "Invite URL"]
    )
    for guest in event.guests:
        writer.writerow(
            [
                guest.name,
                guest.email,
                guest.status,
                guest.party_size,
                guest.party_limit,
                guest.dietary,
                guest.note,
                url_for("public.invite", token=guest.token, _external=True),
            ]
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="event-{event.id}-guests.csv"'},
    )


@bp.post("/events/<int:event_id>/blocks")
@admin_required
def add_block(event_id):
    event = event_for_host(event_id)
    kind = request.form.get("kind", "")
    title = request.form.get("block_title", "").strip()[:180]
    description = request.form.get("block_description", "").strip()[:500]
    raw_items = [
        item.strip() for item in request.form.get("block_items", "").splitlines() if item.strip()
    ]
    if kind not in {"poll", "potluck", "schedule", "info", "photos"} or not title:
        flash("Choose a block type and enter a title.", "error")
        return redirect(url_for("admin.manage_event", event_id=event.id))
    if kind == "photos":
        album_url = raw_items[0] if raw_items else ""
        try:
            parsed = urlsplit(album_url)
            valid = parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid = False
        if not valid:
            flash("Paste a valid HTTP or HTTPS shared-album link in the items box.", "error")
            return redirect(url_for("admin.manage_event", event_id=event.id))
        data = {"url": album_url}
    elif kind in {"poll", "potluck"}:
        data = {"items": raw_items[:30]}
    elif kind == "schedule":
        schedule = []
        for item in raw_items[:30]:
            time_label, separator, label = item.partition("|")
            schedule.append(
                {"time": time_label.strip() if separator else "", "label": label.strip() if separator else time_label.strip()}
            )
        data = {"items": schedule}
    else:
        data = {}
    position = max([block.position for block in event.blocks], default=-1) + 1
    new_block = EventBlock(
            event=event,
            kind=kind,
            title=title,
            description=description,
            data_json=json.dumps(data),
            position=position,
        )
    db.session.add(new_block)
    message = f"A new {kind} was added: {title}."
    guest_activity(event, "event", message)
    db.session.commit()
    send_subscriber_email(event, "New party extra", message)
    send_guest_push(event, "event", f"New on {event.title}", message, None)
    flash("Party extra added.", "success")
    return redirect(url_for("admin.manage_event", event_id=event.id))


@bp.post("/events/<int:event_id>/blocks/<int:block_id>/delete")
@admin_required
def delete_block(event_id, block_id):
    event_for_host(event_id)
    block = EventBlock.query.filter_by(id=block_id, event_id=event_id).first_or_404()
    db.session.delete(block)
    db.session.commit()
    flash("Party extra removed.", "success")
    return redirect(url_for("admin.manage_event", event_id=event_id))


@bp.route("/events/<int:event_id>/decorate", methods=["GET", "POST"])
@admin_required
def decorate_event(event_id):
    event = event_for_host(event_id)
    if request.method == "POST":
        try:
            event.theme_css = clean_css(request.form.get("theme_css", ""))
            event.theme_html_top = clean_html(request.form.get("theme_html_top", ""))
            event.theme_html_bottom = clean_html(request.form.get("theme_html_bottom", ""))
            db.session.commit()
            flash("Theme saved.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("decorate.html", event=event)


@bp.route("/events/<int:event_id>/hosts", methods=["GET", "POST"])
@admin_required
def manage_hosts(event_id):
    event = event_for_host(event_id, owner_only=True)
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()[:120]
        name = request.form.get("name", "").strip()[:120]
        email = request.form.get("email", "").strip()[:255]
        password = request.form.get("password", "")
        if not username or not name:
            flash("Name and username are required.", "error")
        else:
            user = HostUser.query.filter_by(username=username).first()
            if not user:
                if len(password) < 10:
                    flash("A new co-host needs a temporary password of at least 10 characters.", "error")
                    return redirect(url_for("admin.manage_hosts", event_id=event.id))
                user = HostUser(
                    name=name,
                    username=username,
                    email=email,
                    password_hash=generate_password_hash(password),
                )
                db.session.add(user)
                db.session.flush()
            link = EventHost.query.filter_by(event_id=event.id, user_id=user.id).first()
            if not link:
                db.session.add(EventHost(event=event, user=user, role="cohost"))
            db.session.commit()
            flash(f"{user.name} is now a co-host.", "success")
            return redirect(url_for("admin.manage_hosts", event_id=event.id))
    return render_template("hosts.html", event=event, host_links=event.host_links)


@bp.post("/events/<int:event_id>/hosts/<int:user_id>/remove")
@admin_required
def remove_host(event_id, user_id):
    event = event_for_host(event_id, owner_only=True)
    link = EventHost.query.filter_by(event_id=event.id, user_id=user_id, role="cohost").first_or_404()
    db.session.delete(link)
    db.session.commit()
    flash("Co-host access removed.", "success")
    return redirect(url_for("admin.manage_hosts", event_id=event.id))


@bp.post("/events/<int:event_id>/reminders")
@admin_required
def add_reminder(event_id):
    event = event_for_host(event_id)
    message = request.form.get("message", "").strip()[:500]
    send_at = parse_datetime(request.form.get("send_at"))
    if not message or not send_at:
        flash("Choose a date/time and write the reminder.", "error")
    elif send_at <= event_now(event):
        flash("The reminder time must be in the future.", "error")
    else:
        db.session.add(
            Reminder(event=event, created_by=current_host(), send_at=send_at, message=message)
        )
        db.session.commit()
        flash("Reminder scheduled.", "success")
    return redirect(url_for("admin.manage_event", event_id=event.id))


@bp.post("/events/<int:event_id>/reminders/<int:reminder_id>/delete")
@admin_required
def delete_reminder(event_id, reminder_id):
    event = event_for_host(event_id)
    reminder = Reminder.query.filter_by(id=reminder_id, event_id=event.id, sent_at=None).first_or_404()
    db.session.delete(reminder)
    db.session.commit()
    flash("Scheduled reminder removed.", "success")
    return redirect(url_for("admin.manage_event", event_id=event.id))


@bp.post("/events/<int:event_id>/delete")
@admin_required
def delete_event(event_id):
    event = event_for_host(event_id, owner_only=True)
    if request.form.get("confirm_title", "") != event.title:
        flash("The event title did not match, so nothing was deleted.", "error")
        return redirect(url_for("admin.manage_event", event_id=event.id))
    title = event.title
    banner_path = None
    if event.banner_filename:
        uploads = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
        candidate = (uploads / event.banner_filename).resolve()
        if candidate.parent == uploads:
            banner_path = candidate
    db.session.delete(event)
    db.session.commit()
    if banner_path:
        banner_path.unlink(missing_ok=True)
    flash(f"Deleted {title}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/push/subscribe", methods=["GET", "POST"])
@admin_required
def subscribe_push():
    payload = request.get_json(silent=True) or {}
    user = current_host()
    if request.method == "GET":
        return jsonify(subscription_state(request.args.get("endpoint", ""), host_user=user))
    if not isinstance(payload, dict):
        return jsonify(error="Invalid notification settings."), 400
    if payload.get("disabled"):
        remove_subscription(payload.get("endpoint", ""), host_user=user)
    else:
        try:
            save_subscription(payload.get("subscription") or {}, payload.get("categories") or [], host_user=user)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    db.session.commit()
    return jsonify(ok=True, public_key=public_vapid_key())


@bp.get("/push/key")
@admin_required
def push_key():
    return jsonify(public_key=public_vapid_key())

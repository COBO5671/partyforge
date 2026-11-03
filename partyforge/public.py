import json
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from . import db
from .event_time import event_now
from .models import BlockResponse, Event, EventBlock, Guest
from .notifications import (
    guest_activity,
    host_notification,
    send_host_email,
    send_subscriber_email,
    update_subscription,
)
from .push import subscription_state, public_vapid_key, remove_subscription, save_subscription, send_guest_push, send_host_push

bp = Blueprint("public", __name__)


def block_views(event, current_guest=None):
    views = []
    for block in event.blocks:
        item = {"block": block, "data": block.data, "mine": None}
        if current_guest:
            response = BlockResponse.query.filter_by(
                block_id=block.id, guest_id=current_guest.id
            ).first()
            item["mine"] = response.value if response else None
        if block.kind == "poll":
            votes = Counter()
            for response in block.responses:
                choice = response.value.get("choice")
                if choice:
                    votes[choice] += 1
            item["counts"] = votes
            item["total"] = sum(votes.values())
        if block.kind == "potluck":
            claims = []
            for response in sorted(block.responses, key=lambda item: item.updated_at):
                choice = response.value.get("choice")
                if choice:
                    claims.append(
                        {
                            "item": choice,
                            "guest_name": response.guest.name,
                            "guest_id": response.guest_id,
                        }
                    )
            item["claims"] = claims
        views.append(item)
    return views


def render_event(event, guest=None, open_link=False):
    attendees = []
    if event.show_guest_list:
        attendees = Guest.query.filter_by(event_id=event.id, status="yes").order_by(Guest.name).all()
    try:
        event_zone = ZoneInfo(event.timezone or "America/Chicago")
    except ZoneInfoNotFoundError:
        event_zone = ZoneInfo("America/Chicago")
    event_start = event.start_at.replace(tzinfo=event_zone)
    deadline = event.settings.rsvp_deadline if event.settings else None
    deadline_passed = bool(deadline and deadline < event_now(event))
    # Filter before limiting so older declines cannot crowd out visible updates.
    activities = []
    if guest and guest.status != "pending":
        activities = [
            item for item in event.activities
            if item.kind != "rsvp" or (
                event.show_guest_list
                and not (item.actor and item.actor.status == "no")
                and not item.message.endswith(" is can’t go.")
            )
        ][:20]
    return render_template(
        "public_event.html",
        event=event,
        guest=guest,
        open_link=open_link,
        attendees=attendees,
        block_views=block_views(event, guest),
        event_start_ms=int(event_start.timestamp() * 1000),
        event_timezone_label=event_start.tzname() or event.timezone,
        celebrate=bool(guest and session.pop("celebrate_guest", None) == guest.id),
        activities=activities,
        subscribed=bool(guest and guest.subscription and guest.subscription.all_updates),
        rsvp_deadline=deadline,
        deadline_passed=deadline_passed,
        vapid_public_key=public_vapid_key(),
    )


@bp.route("/i/<token>", methods=["GET", "POST"])
def invite(token):
    guest = Guest.query.filter_by(token=token).first_or_404()
    event = guest.event
    if request.method == "POST":
        old_status = guest.status
        deadline = event.settings.rsvp_deadline if event.settings else None
        if deadline and deadline < event_now(event) and guest.status == "pending":
            flash("The RSVP deadline has passed. Contact the host if you need to respond.", "error")
            return redirect(url_for("public.invite", token=token))
        status = request.form.get("status", "")
        if status not in {"yes", "maybe", "no"}:
            flash("Please choose yes, maybe, or no.", "error")
            return redirect(url_for("public.invite", token=token))
        try:
            party_size = int(request.form.get("party_size", "1"))
        except ValueError:
            party_size = 1
        guest.status = status
        guest.party_size = max(1, min(guest.party_limit, party_size))
        guest.dietary = request.form.get("dietary", "").strip()[:500]
        guest.note = request.form.get("note", "").strip()[:1000]
        guest.email = request.form.get("email", guest.email or "").strip()[:255]
        wants_updates = request.form.get("subscribe_all") == "on"
        update_subscription(guest, wants_updates)
        status_label = {"yes": "Going", "maybe": "Maybe", "no": "Can’t go"}[status]
        host_message = f"{guest.name} responded {status_label} for {guest.party_size}."
        host_notification(event, "rsvp", f"RSVP: {guest.name}", host_message, guest)
        share_rsvp = event.show_guest_list and status != "no" and old_status != status
        if share_rsvp:
            public_message = f"{guest.name} is {status_label.lower()}."
            guest_activity(event, "rsvp", public_message, guest)
        db.session.commit()
        send_host_email(event, f"RSVP from {guest.name}", host_message)
        send_host_push(event, "rsvp", f"RSVP: {guest.name}", host_message, f"/admin/events/{event.id}")
        if share_rsvp:
            send_subscriber_email(event, "RSVP update", public_message, guest)
            send_guest_push(event, "rsvp", "RSVP update", public_message, None, guest)
        if guest.status == "yes":
            session["celebrate_guest"] = guest.id
        flash("Your RSVP is saved — you can return to this link anytime.", "success")
        return redirect(url_for("public.invite", token=token))
    return render_event(event, guest=guest)


@bp.route("/e/<token>", methods=["GET", "POST"])
def open_event(token):
    event = Event.query.filter_by(public_token=token).first_or_404()
    if request.method == "POST":
        if not event.allow_open_rsvp:
            abort(403)
        deadline = event.settings.rsvp_deadline if event.settings else None
        if deadline and deadline < event_now(event):
            flash("The RSVP deadline has passed. Contact the host if you need to respond.", "error")
            return redirect(url_for("public.open_event", token=token))
        name = request.form.get("name", "").strip()[:160]
        if not name:
            flash("Please enter your name.", "error")
            return redirect(url_for("public.open_event", token=token))
        guest = Guest(
            event=event,
            name=name,
            email=request.form.get("email", "").strip()[:255],
            party_limit=10,
            status=request.form.get("status", "yes")
            if request.form.get("status") in {"yes", "maybe", "no"}
            else "yes",
        )
        try:
            guest.party_size = max(1, min(10, int(request.form.get("party_size", "1"))))
        except ValueError:
            guest.party_size = 1
        guest.dietary = request.form.get("dietary", "").strip()[:500]
        guest.note = request.form.get("note", "").strip()[:1000]
        db.session.add(guest)
        db.session.flush()
        update_subscription(guest, request.form.get("subscribe_all") == "on")
        status_label = {"yes": "Going", "maybe": "Maybe", "no": "Can’t go"}[guest.status]
        host_message = f"{guest.name} joined through the open invite: {status_label}, party of {guest.party_size}."
        host_notification(event, "rsvp", f"New RSVP: {guest.name}", host_message, guest)
        share_rsvp = event.show_guest_list and guest.status != "no"
        if share_rsvp:
            public_message = f"{guest.name} is {status_label.lower()}."
            guest_activity(event, "rsvp", public_message, guest)
        db.session.commit()
        send_host_email(event, f"New RSVP from {guest.name}", host_message)
        send_host_push(event, "rsvp", f"New RSVP: {guest.name}", host_message, f"/admin/events/{event.id}")
        if share_rsvp:
            send_subscriber_email(event, "RSVP update", public_message, guest)
            send_guest_push(event, "rsvp", "RSVP update", public_message, None, guest)
        if guest.status == "yes":
            session["celebrate_guest"] = guest.id
        flash("You are on the list. Save this personalized link.", "success")
        return redirect(url_for("public.invite", token=guest.token))
    return render_event(event, open_link=True)


@bp.post("/i/<token>/blocks/<int:block_id>")
def answer_block(token, block_id):
    guest = Guest.query.filter_by(token=token).first_or_404()
    block = EventBlock.query.filter_by(id=block_id, event_id=guest.event_id).first_or_404()
    if block.kind not in {"poll", "potluck"}:
        abort(400)
    if guest.status == "pending":
        flash("RSVP first, then you can vote and add what you’re bringing.", "error")
        return redirect(url_for("public.invite", token=token) + "#rsvp")
    choice = request.form.get("choice", "").strip()
    response = BlockResponse.query.filter_by(block_id=block.id, guest_id=guest.id).first()
    if block.kind == "poll":
        valid_items = block.data.get("items", [])
        if choice not in valid_items:
            abort(400)
    else:
        if request.form.get("clear") == "1":
            if response:
                old_choice = response.value.get("choice", "")
                db.session.delete(response)
                message = f"{guest.name} removed {old_choice or 'their item'} from {block.title}."
                host_notification(guest.event, "potluck", "Potluck item removed", message, guest)
                guest_activity(guest.event, "potluck", message, guest)
                db.session.commit()
                send_host_email(guest.event, "Potluck item removed", message)
                send_subscriber_email(guest.event, "Potluck update", message, guest)
                send_host_push(guest.event, "potluck", "Potluck item removed", message, f"/admin/events/{guest.event.id}")
                send_guest_push(guest.event, "potluck", "Potluck update", message, None, guest)
            flash("Your potluck contribution was removed.", "success")
            return redirect(url_for("public.invite", token=token))
        choice = choice[:160]
        if not choice:
            flash("Tell everyone what you’re bringing first.", "error")
            return redirect(url_for("public.invite", token=token))
    if not response:
        response = BlockResponse(block_id=block.id, guest_id=guest.id)
        db.session.add(response)
    response.value_json = json.dumps({"choice": choice})
    if block.kind == "potluck":
        message = f"{guest.name} is bringing {choice}."
        host_notification(guest.event, "potluck", f"Potluck: {guest.name}", message, guest)
        guest_activity(guest.event, "potluck", message, guest)
    else:
        message = f"{guest.name} responded to the poll “{block.title}.”"
        host_notification(guest.event, "poll", f"Poll response: {guest.name}", message, guest)
        guest_activity(guest.event, "poll", message, guest)
    db.session.commit()
    send_host_email(guest.event, "Potluck update" if block.kind == "potluck" else "New poll response", message)
    send_subscriber_email(guest.event, "Potluck update" if block.kind == "potluck" else "Poll update", message, guest)
    push_category = "potluck" if block.kind == "potluck" else "polls"
    push_title = "Potluck update" if block.kind == "potluck" else "Poll update"
    send_host_push(guest.event, push_category, push_title, message, f"/admin/events/{guest.event.id}")
    send_guest_push(guest.event, push_category, push_title, message, None, guest)
    flash(
        "What you’re bringing is saved to your private guest link."
        if block.kind == "potluck"
        else "Your choice is saved.",
        "success",
    )
    return redirect(url_for("public.invite", token=token))


@bp.route("/i/<token>/push/subscribe", methods=["GET", "POST"])
def subscribe_push(token):
    guest = Guest.query.filter_by(token=token).first_or_404()
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        return jsonify(subscription_state(request.args.get("endpoint", ""), guest=guest))
    if not isinstance(payload, dict):
        return jsonify(error="Invalid notification settings."), 400
    if payload.get("disabled"):
        remove_subscription(payload.get("endpoint", ""), guest=guest)
    else:
        try:
            save_subscription(payload.get("subscription") or {}, payload.get("categories") or [], guest=guest)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    db.session.commit()
    return jsonify(ok=True, public_key=public_vapid_key())

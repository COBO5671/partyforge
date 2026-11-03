import json
import secrets
from datetime import datetime

from . import db


def make_token():
    return secrets.token_urlsafe(12)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    subtitle = db.Column(db.String(240), default="")
    description = db.Column(db.Text, default="")
    location = db.Column(db.String(300), default="")
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime)
    timezone = db.Column(db.String(64), default="America/Chicago")
    banner_filename = db.Column(db.String(255))
    public_token = db.Column(db.String(32), unique=True, default=make_token, nullable=False)
    allow_open_rsvp = db.Column(db.Boolean, default=False)
    show_guest_list = db.Column(db.Boolean, default=True)
    theme_css = db.Column(db.Text, default="")
    theme_html_top = db.Column(db.Text, default="")
    theme_html_bottom = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    guests = db.relationship(
        "Guest", backref="event", cascade="all, delete-orphan", lazy=True
    )
    blocks = db.relationship(
        "EventBlock",
        backref="event",
        cascade="all, delete-orphan",
        order_by="EventBlock.position",
        lazy=True,
    )
    activities = db.relationship(
        "EventActivity",
        backref="event",
        cascade="all, delete-orphan",
        order_by="EventActivity.created_at.desc()",
        lazy=True,
    )
    notifications = db.relationship(
        "Notification", backref="event", cascade="all, delete-orphan", lazy=True
    )
    settings = db.relationship(
        "EventSettings", backref="event", cascade="all, delete-orphan", uselist=False
    )
    host_links = db.relationship(
        "EventHost", backref="event", cascade="all, delete-orphan", lazy=True
    )
    reminders = db.relationship(
        "Reminder", backref="event", cascade="all, delete-orphan", lazy=True
    )
    highlights = db.relationship(
        "EventHighlight", backref="event", cascade="all, delete-orphan",
        order_by="EventHighlight.position", lazy=True,
    )


class EventHighlight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    title = db.Column(db.String(60), nullable=False)
    body = db.Column(db.String(240), nullable=False)
    position = db.Column(db.Integer, default=0)


class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(255), default="")
    token = db.Column(db.String(40), unique=True, default=make_token, nullable=False)
    party_limit = db.Column(db.Integer, default=1)
    status = db.Column(db.String(16), default="pending")
    party_size = db.Column(db.Integer, default=1)
    dietary = db.Column(db.String(500), default="")
    note = db.Column(db.String(1000), default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subscription = db.relationship(
        "GuestSubscription",
        backref="guest",
        cascade="all, delete-orphan",
        uselist=False,
    )
    push_subscriptions = db.relationship(
        "PushSubscription", backref="guest", cascade="all, delete-orphan", lazy=True
    )


class EventBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    kind = db.Column(db.String(24), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.String(500), default="")
    data_json = db.Column(db.Text, default="{}")
    position = db.Column(db.Integer, default=0)

    @property
    def data(self):
        try:
            return json.loads(self.data_json or "{}")
        except json.JSONDecodeError:
            return {}


class BlockResponse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("event_block.id"), nullable=False)
    guest_id = db.Column(db.Integer, db.ForeignKey("guest.id"), nullable=False)
    value_json = db.Column(db.Text, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    block = db.relationship(
        "EventBlock",
        backref=db.backref("responses", cascade="all, delete-orphan", lazy=True),
    )
    guest = db.relationship("Guest")

    __table_args__ = (
        db.UniqueConstraint("block_id", "guest_id", name="uq_block_guest"),
    )

    @property
    def value(self):
        try:
            return json.loads(self.value_json or "{}")
        except json.JSONDecodeError:
            return {}


class GuestSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey("guest.id"), unique=True, nullable=False)
    all_updates = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    actor_guest_id = db.Column(db.Integer, db.ForeignKey("guest.id"))
    kind = db.Column(db.String(32), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship("Guest")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    actor_guest_id = db.Column(db.Integer, db.ForeignKey("guest.id"))
    kind = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    read_at = db.Column(db.DateTime)

    actor = db.relationship("Guest")
    reads = db.relationship(
        "NotificationRead", backref="notification", cascade="all, delete-orphan", lazy=True
    )


class NotificationRead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey("notification.id"), nullable=False)
    host_user_id = db.Column(db.Integer, db.ForeignKey("host_user.id"), nullable=False)
    read_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("notification_id", "host_user_id", name="uq_notification_host_read"),
    )


class EventSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), unique=True, nullable=False)
    rsvp_deadline = db.Column(db.DateTime)


class HostUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(255), default="")
    password_hash = db.Column(db.String(255), nullable=False)
    is_owner = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    event_links = db.relationship(
        "EventHost", backref="user", cascade="all, delete-orphan", lazy=True
    )
    push_subscriptions = db.relationship(
        "PushSubscription", backref="host_user", cascade="all, delete-orphan", lazy=True
    )


class EventHost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("host_user.id"), nullable=False)
    role = db.Column(db.String(20), default="cohost", nullable=False)

    __table_args__ = (db.UniqueConstraint("event_id", "user_id", name="uq_event_host"),)


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.Text, nullable=False)
    keys_json = db.Column(db.Text, default="{}", nullable=False)
    categories_json = db.Column(db.Text, default="[]", nullable=False)
    guest_id = db.Column(db.Integer, db.ForeignKey("guest.id"))
    host_user_id = db.Column(db.Integer, db.ForeignKey("host_user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def categories(self):
        try:
            return set(json.loads(self.categories_json or "[]"))
        except json.JSONDecodeError:
            return set()

    @property
    def subscription_info(self):
        try:
            keys = json.loads(self.keys_json or "{}")
        except json.JSONDecodeError:
            keys = {}
        return {"endpoint": self.endpoint, "keys": keys}


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("host_user.id"))
    send_at = db.Column(db.DateTime, nullable=False)
    message = db.Column(db.String(500), nullable=False)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship("HostUser")

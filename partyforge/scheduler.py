import threading
from datetime import datetime

from . import db
from .event_time import event_now
from .models import EventActivity, Reminder
from .notifications import send_subscriber_email
from .push import send_guest_push


def send_due_reminders(app):
    with app.app_context():
        due = Reminder.query.filter(Reminder.sent_at.is_(None)).all()
        for reminder in due:
            event = reminder.event
            if reminder.send_at > event_now(event):
                continue
            db.session.add(
                EventActivity(event=event, kind="announcement", message=reminder.message)
            )
            reminder.sent_at = datetime.now()
            db.session.commit()
            send_guest_push(
                event,
                "reminders",
                f"Reminder: {event.title}",
                reminder.message,
                None,
            )
            send_subscriber_email(event, "Event reminder", reminder.message)


def start_reminder_scheduler(app):
    interval = max(30, int(app.config.get("REMINDER_POLL_SECONDS", 60)))

    def run():
        try:
            send_due_reminders(app)
        except Exception:
            app.logger.exception("Reminder scheduler failed")
        timer = threading.Timer(interval, run)
        timer.daemon = True
        timer.start()

    timer = threading.Timer(2, run)
    timer.daemon = True
    timer.start()

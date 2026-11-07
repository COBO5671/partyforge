import os
import re
import tempfile
import unittest
import json
from datetime import datetime
from unittest.mock import patch


class PartyForgeSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["UPLOAD_FOLDER"] = self.tempdir.name
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["ADMIN_PASSWORD"] = "test-password"
        os.environ["ADMIN_USERNAME"] = "cody"
        os.environ["VAPID_PRIVATE_KEY"] = os.path.join(self.tempdir.name, "vapid.pem")
        os.environ["VAPID_PUBLIC_KEY"] = os.path.join(self.tempdir.name, "vapid.txt")

        from partyforge import create_app

        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def csrf(self, response):
        match = re.search(rb'name="_csrf" value="([^"]+)"', response.data)
        if not match:
            match = re.search(rb'data-csrf="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def login(self):
        page = self.client.get("/admin/login")
        response = self.client.post(
            "/admin/login",
            data={"_csrf": self.csrf(page), "password": "test-password"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Events", response.data)

    def test_description_previews_only_trusted_tiktok_urls(self):
        from partyforge.security import description_content
        result = description_content('Example https://www.tiktok.com/@host/video/7675445872582216973?tracking=1 <script>alert(1)</script>')
        self.assertEqual(len(result['videos']), 1)
        self.assertEqual(result['videos'][0]['url'], 'https://www.tiktok.com/@host/video/7675445872582216973')
        self.assertNotIn('<script', result['html'])
        self.assertNotIn('tracking=1', result['html'])
        result = description_content('<a href="https://www.tiktok.com/@host/video/7675445872582216973">Example</a> https://www.tiktok.com/@host/video/7675445872582216973')
        self.assertEqual(len(result['videos']), 1)
        for url in ['https://tiktok.com.evil.test/@a/video/7675445872582216973', 'https://tiktok.com@evil.test/@a/video/7675445872582216973', 'javascript:alert(1)', 'https://www.tiktok.com/@a/video/not-a-number']:
            self.assertEqual(description_content(url)['videos'], [])
        self.assertIn('href="https://example.com"', description_content('https://example.com')['html'])

    def test_highlights_saved_and_guest_flow_with_video(self):
        self.login()
        page = self.client.get('/admin/events/new')
        response = self.client.post('/admin/events/new', data={
            '_csrf': self.csrf(page), 'title': 'Universal event',
            'start_at': '2030-01-01T18:00', 'timezone': 'America/Chicago',
            'allow_open_rsvp': 'on', 'location': 'Main hall',
            'description': 'https://www.tiktok.com/@host/video/7675445872582216973',
            'highlights_present': '1', 'highlight_title_0': 'Parking',
            'highlight_body_0': 'Use the north entrance.',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        from partyforge import db
        from partyforge.models import Event, Guest, EventBlock
        with self.app.app_context():
            event = Event.query.one()
            self.assertEqual(event.highlights[0].body, 'Use the north entrance.')
            guest = Guest(event=event, name='Test guest', status='yes')
            db.session.add_all([guest, EventBlock(event=event, kind='potluck', title='Bring something')])
            db.session.commit()
            token = guest.token
            event_id = event.id
        page = self.client.get(f'/i/{token}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'referrerpolicy="no-referrer"', page.data)
        self.assertIn(b'https://www.tiktok.com/player/v1/7675445872582216973', page.data)
        self.assertLess(page.data.index(b'Use the north entrance.'), page.data.index(b'id="rsvp"'))
        self.assertLess(page.data.index(b'id="rsvp"'), page.data.index(b'block-potluck'))
        self.assertLess(page.data.index(b'block-potluck'), page.data.index(b'data-push-panel'))
        edit = self.client.get(f'/admin/events/{event_id}/edit')
        self.assertIn(b'Use the north entrance.', edit.data)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_root_redirects_to_organizer_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/login"))

    def test_create_event_and_open_public_page(self):
        self.login()
        page = self.client.get("/admin/events/new")
        response = self.client.post(
            "/admin/events/new",
            data={
                "_csrf": self.csrf(page),
                "title": "Bonfire test",
                "subtitle": "Bring a chair",
                "start_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
                "location": "Backyard",
                "timezone": "America/Chicago",
                "allow_open_rsvp": "on",
                "show_guest_list": "on",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Bonfire test", response.data)

        from partyforge.models import Event

        with self.app.app_context():
            event = Event.query.one()
            public_token = event.public_token

        invite = self.client.get(f"/e/{public_token}")
        self.assertEqual(invite.status_code, 200)
        self.assertIn(b"Bring a chair", invite.data)
        self.assertIn(b"data-countdown", invite.data)
        self.assertIn(b"calendar-tile", invite.data)

    def test_description_renders_saved_break_tags_instead_of_showing_them(self):
        from partyforge import db
        from partyforge.models import Event

        with self.app.app_context():
            event = Event(
                title="Formatted event",
                start_at=datetime.now(),
                description="First line&lt;br&gt;Second line<BR>Third line<p><strong>Important</strong></p>",
            )
            db.session.add(event)
            db.session.commit()
            token = event.public_token

        page = self.client.get(f"/e/{token}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"First line<br>Second line<br>Third line", page.data)
        self.assertIn(b"<strong>Important</strong>", page.data)
        self.assertNotIn(b"&lt;br", page.data)

    def test_potluck_free_text_is_saved_to_the_guest(self):
        from partyforge import db
        from partyforge.models import BlockResponse, Event, EventBlock, Guest

        with self.app.app_context():
            event = Event(title="Friendsgiving", start_at=datetime.now())
            guest = Guest(event=event, name="Austin", status="yes")
            block = EventBlock(
                event=event,
                kind="potluck",
                title="What are you bringing?",
                data_json=json.dumps({"items": []}),
            )
            db.session.add(event)
            db.session.commit()
            token = guest.token
            block_id = block.id

        invite = self.client.get(f"/i/{token}")
        response = self.client.post(
            f"/i/{token}/blocks/{block_id}",
            data={
                "_csrf": self.csrf(invite),
                "choice": "Green bean casserole",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Green bean casserole", response.data)
        self.assertIn(b"Austin", response.data)

        with self.app.app_context():
            saved = BlockResponse.query.one()
            self.assertEqual(saved.guest.name, "Austin")
            self.assertEqual(saved.value["choice"], "Green bean casserole")

    def test_rsvp_creates_host_notification_and_guest_subscription(self):
        from partyforge import db
        from partyforge.models import Event, Guest, GuestSubscription, Notification

        with self.app.app_context():
            event = Event(title="Friendsgiving", start_at=datetime.now())
            guest = Guest(event=event, name="Austin")
            db.session.add(event)
            db.session.commit()
            token = guest.token

        invite = self.client.get(f"/i/{token}")
        response = self.client.post(
            f"/i/{token}",
            data={
                "_csrf": self.csrf(invite),
                "status": "yes",
                "party_size": "1",
                "email": "austin@example.com",
                "subscribe_all": "on",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email me all updates", response.data)

        with self.app.app_context():
            self.assertEqual(Notification.query.count(), 1)
            self.assertTrue(GuestSubscription.query.one().all_updates)

    def test_potluck_creates_activity_and_host_alert(self):
        from partyforge import db
        from partyforge.models import Event, EventActivity, EventBlock, Guest, Notification

        with self.app.app_context():
            event = Event(title="Friendsgiving", start_at=datetime.now())
            guest = Guest(event=event, name="Austin", status="yes")
            block = EventBlock(
                event=event,
                kind="potluck",
                title="Food",
                data_json=json.dumps({"items": []}),
            )
            db.session.add(event)
            db.session.commit()
            token = guest.token
            block_id = block.id

        invite = self.client.get(f"/i/{token}")
        response = self.client.post(
            f"/i/{token}/blocks/{block_id}",
            data={"_csrf": self.csrf(invite), "choice": "Pumpkin pie"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Event activity", response.data)
        self.assertIn(b"Austin is bringing Pumpkin pie", response.data)

        with self.app.app_context():
            self.assertEqual(Notification.query.count(), 1)
            self.assertEqual(EventActivity.query.count(), 1)

    def test_guest_can_subscribe_to_browser_categories_without_email(self):
        from partyforge import db
        from partyforge.models import Event, Guest, PushSubscription

        with self.app.app_context():
            event = Event(title="Bonfire", start_at=datetime.now())
            guest = Guest(event=event, name="Hannah", status="yes")
            db.session.add(event)
            db.session.commit()
            token = guest.token

        invite = self.client.get(f"/i/{token}")
        response = self.client.post(
            f"/i/{token}/push/subscribe",
            json={
                "subscription": {
                    "endpoint": "https://push.example/subscription-1",
                    "keys": {"p256dh": "test-public-key", "auth": "test-auth"},
                },
                "categories": ["potluck", "rsvp", "not-a-real-category"],
            },
            headers={"X-CSRF-Token": self.csrf(invite)},
        )
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            item = PushSubscription.query.one()
            self.assertEqual(item.categories, {"potluck", "rsvp"})
            self.assertEqual(item.guest.email, "")

    def test_rsvp_deadline_blocks_only_an_unanswered_guest(self):
        from datetime import timedelta

        from partyforge import db
        from partyforge.models import Event, EventSettings, Guest

        with self.app.app_context():
            event = Event(title="Dinner", start_at=datetime.now())
            event.settings = EventSettings(rsvp_deadline=datetime.now() - timedelta(days=1))
            guest = Guest(event=event, name="Mary Ann")
            db.session.add(event)
            db.session.commit()
            token = guest.token

        invite = self.client.get(f"/i/{token}")
        response = self.client.post(
            f"/i/{token}",
            data={"_csrf": self.csrf(invite), "status": "yes", "party_size": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"RSVP deadline has passed", response.data)
        with self.app.app_context():
            self.assertEqual(Guest.query.one().status, "pending")

    def test_notification_settings_are_scoped_and_survive_reload(self):
        from partyforge import db
        from partyforge.models import Event, Guest
        with self.app.app_context():
            event = Event(title="Dinner", start_at=datetime.now())
            first = Guest(event=event, name="First")
            second = Guest(event=event, name="Second")
            db.session.add(event)
            db.session.commit()
            tokens = [first.token, second.token]
        endpoint = "https://push.example/shared-browser"
        for token in tokens:
            page = self.client.get(f"/i/{token}")
            self.assertIn(b"data-push-panel", page.data)
            result = self.client.post(f"/i/{token}/push/subscribe", json={
                "subscription": {"endpoint": endpoint, "keys": {"p256dh": "key", "auth": "auth"}},
                "categories": ["reminders"],
            }, headers={"X-CSRF-Token": self.csrf(page)})
            self.assertEqual(result.status_code, 200)
        path = f"/i/{tokens[0]}/push/subscribe"
        self.assertEqual(self.client.get(path, query_string={"endpoint": endpoint}).json,
                         {"subscribed": True, "categories": ["reminders"]})
        self.client.post(path, json={"disabled": True, "endpoint": endpoint},
                         headers={"X-CSRF-Token": self.csrf(page)})
        self.assertFalse(self.client.get(path, query_string={"endpoint": endpoint}).json["subscribed"])
        self.assertTrue(self.client.get(f"/i/{tokens[1]}/push/subscribe",
                                       query_string={"endpoint": endpoint}).json["subscribed"])
        bad = self.client.post(path, json={"subscription": "invalid"},
                               headers={"X-CSRF-Token": self.csrf(page)})
        self.assertEqual(bad.status_code, 400)

    def test_deadline_uses_event_clock(self):
        from partyforge import db
        from partyforge.models import Event, EventSettings, Guest
        with self.app.app_context():
            event = Event(title="Dinner", start_at=datetime(2030, 1, 2))
            event.settings = EventSettings(rsvp_deadline=datetime(2030, 1, 1, 18))
            guest = Guest(event=event, name="Guest")
            db.session.add(event)
            db.session.commit()
            token = guest.token
        with patch("partyforge.public.event_now", return_value=datetime(2030, 1, 1, 17)):
            page = self.client.get(f"/i/{token}")
            self.assertNotIn(b"The RSVP deadline has passed", page.data)
        with patch("partyforge.public.event_now", return_value=datetime(2030, 1, 1, 19)):
            page = self.client.get(f"/i/{token}")
            self.assertIn(b"The RSVP deadline has passed", page.data)

    def test_future_reminder_is_not_sent_in_event_timezone(self):
        from partyforge import db
        from partyforge.models import Event, Reminder
        from partyforge.scheduler import send_due_reminders
        with self.app.app_context():
            event = Event(title="Dinner", start_at=datetime(2030, 1, 2))
            db.session.add(Reminder(event=event, send_at=datetime(2030, 1, 1, 18), message="Hello"))
            db.session.commit()
        with patch("partyforge.scheduler.event_now", return_value=datetime(2030, 1, 1, 17)), patch("partyforge.scheduler.send_guest_push") as push:
            send_due_reminders(self.app)
            push.assert_not_called()

    def test_static_urls_use_content_versions(self):
        import hashlib
        from pathlib import Path
        from flask import url_for
        with self.app.test_request_context():
            expected = hashlib.sha256((Path(self.app.static_folder) / "app.css").read_bytes()).hexdigest()[:12]
            self.assertIn("v=" + expected, url_for("static", filename="app.css"))

    def test_owner_can_delete_event_and_related_data(self):
        from partyforge import db
        from partyforge.models import Event, EventHost, Guest, HostUser

        self.login()
        with self.app.app_context():
            owner = HostUser.query.filter_by(is_owner=True).one()
            event = Event(title="Delete me", start_at=datetime.now())
            db.session.add(event)
            db.session.flush()
            db.session.add(EventHost(event=event, user=owner, role="owner"))
            db.session.add(Guest(event=event, name="Guest"))
            db.session.commit()
            event_id = event.id

        page = self.client.get(f"/admin/events/{event_id}")
        response = self.client.post(
            f"/admin/events/{event_id}/delete",
            data={"_csrf": self.csrf(page), "confirm_title": "Delete me"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Deleted Delete me", response.data)
        with self.app.app_context():
            self.assertEqual(Event.query.count(), 0)
            self.assertEqual(Guest.query.count(), 0)

    def test_cohost_can_manage_but_cannot_delete_event(self):
        from werkzeug.security import generate_password_hash

        from partyforge import db
        from partyforge.models import Event, EventHost, HostUser

        with self.app.app_context():
            owner = HostUser.query.filter_by(is_owner=True).one()
            cohost = HostUser(
                name="Josh",
                username="josh",
                password_hash=generate_password_hash("cohost-password"),
            )
            event = Event(title="Shared event", start_at=datetime.now())
            db.session.add_all([cohost, event])
            db.session.flush()
            db.session.add_all(
                [
                    EventHost(event=event, user=owner, role="owner"),
                    EventHost(event=event, user=cohost, role="cohost"),
                ]
            )
            db.session.commit()
            event_id = event.id
            cohost_id = cohost.id

        with self.client.session_transaction() as session:
            session["is_admin"] = True
            session["host_user_id"] = cohost_id
            session["_csrf"] = "cohost-csrf"
        self.assertEqual(self.client.get(f"/admin/events/{event_id}").status_code, 200)
        response = self.client.post(
            f"/admin/events/{event_id}/delete",
            data={"_csrf": "cohost-csrf", "confirm_title": "Shared event"},
        )
        self.assertEqual(response.status_code, 404)

    def test_due_reminder_is_marked_sent_and_added_to_activity(self):
        from datetime import timedelta

        from partyforge import db
        from partyforge.event_time import event_now
        from partyforge.models import Event, EventActivity, Reminder
        from partyforge.scheduler import send_due_reminders

        with self.app.app_context():
            event = Event(title="Dinner", start_at=datetime.now())
            reminder = Reminder(
                event=event,
                send_at=event_now(event) - timedelta(minutes=1),
                message="RSVPs are due today.",
            )
            db.session.add(event)
            db.session.commit()

        with patch("partyforge.scheduler.send_guest_push") as push, patch(
            "partyforge.scheduler.send_subscriber_email"
        ) as email:
            send_due_reminders(self.app)
            push.assert_called_once()
            email.assert_called_once()

        with self.app.app_context():
            self.assertIsNotNone(Reminder.query.one().sent_at)
            self.assertEqual(EventActivity.query.one().message, "RSVPs are due today.")


    def test_shared_and_pending_invites_show_updates_but_hide_declines(self):
        from datetime import timedelta
        from partyforge import db
        from partyforge.models import Event, EventActivity, Guest

        with self.app.app_context():
            event = Event(title="Shared activity", start_at=datetime.now(), allow_open_rsvp=True)
            viewer = Guest(event=event, name="Viewer", status="pending")
            going = Guest(event=event, name="Going guest", status="yes")
            maybe = Guest(event=event, name="Maybe guest", status="maybe")
            declined = Guest(event=event, name="Declined guest", status="no")
            db.session.add(event)
            for actor, kind, message in [(going, "rsvp", "Going guest is going."), (maybe, "rsvp", "Maybe guest is maybe."), (going, "potluck", "Going guest is bringing pie.")]:
                db.session.add(EventActivity(event=event, actor=actor, kind=kind, message=message, created_at=datetime.now() - timedelta(days=1)))
            # Old declines must stay hidden even if the actor later says yes.
            # Filter before applying the 20-item limit.
            for n in range(25):
                db.session.add(EventActivity(event=event, actor=going, kind="rsvp", message="Legacy guest is can" + ("'" if n % 2 else "\u2019") + "t go."))
            db.session.add(EventActivity(event=event, actor=declined, kind="rsvp", message="Declined guest is going."))
            db.session.commit()
            urls = [f"/e/{event.public_token}", f"/i/{viewer.token}", f"/i/{going.token}"]
            event_id = event.id

        for url in urls:
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            for message in (b"Going guest is going.", b"Maybe guest is maybe.", b"Going guest is bringing pie."):
                self.assertIn(message, page.data)
            self.assertNotIn(b"Legacy guest", page.data)
            self.assertNotIn(b"Declined guest", page.data)

        with self.app.app_context():
            db.session.get(Event, event_id).show_guest_list = False
            db.session.commit()
        for url in urls:
            page = self.client.get(url)
            self.assertNotIn(b"Going guest is going.", page.data)
            self.assertNotIn(b"Maybe guest is maybe.", page.data)
            self.assertIn(b"Going guest is bringing pie.", page.data)

    def test_decline_notifies_only_host_while_yes_maybe_are_public(self):
        from partyforge import db
        from partyforge.models import Event, EventActivity, Guest, Notification
        with self.app.app_context():
            event = Event(title="Privacy", start_at=datetime.now(), allow_open_rsvp=True)
            guest = Guest(event=event, name="Responder", status="pending")
            db.session.add(event)
            db.session.commit()
            token, shared_token = guest.token, event.public_token
        for status in ("no", "yes", "maybe"):
            page = self.client.get(f"/i/{token}")
            with patch("partyforge.public.send_host_email") as host_email, patch("partyforge.public.send_subscriber_email") as guest_email, patch("partyforge.public.send_host_push"), patch("partyforge.public.send_guest_push") as guest_push:
                result = self.client.post(f"/i/{token}", data={"_csrf": self.csrf(page), "status": status}, follow_redirects=True)
                self.assertEqual(result.status_code, 200)
                host_email.assert_called_once()
                self.assertEqual(guest_email.call_count, 0 if status == "no" else 1)
                self.assertEqual(guest_push.call_count, 0 if status == "no" else 1)
            if status != "no":
                shared = self.client.get(f"/e/{shared_token}")
                self.assertIn(f"Responder is {'going' if status == 'yes' else 'maybe'}.".encode(), shared.data)
        with self.app.app_context():
            self.assertEqual(Notification.query.count(), 3)
            self.assertEqual(EventActivity.query.count(), 2)


if __name__ == "__main__":
    unittest.main()

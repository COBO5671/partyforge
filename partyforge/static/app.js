function copyText(text, button) {
  navigator.clipboard.writeText(text).then(() => {
    const old = button.textContent;
    button.textContent = "Copied!";
    setTimeout(() => button.textContent = old, 1400);
  });
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", () => copyText(button.dataset.copy, button));
});

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", () => {
    const field = document.getElementById(button.dataset.copyTarget);
    copyText(field.value, button);
  });
});

const promptButton = document.getElementById("make-prompt");
const promptField = document.getElementById("ai-prompt");
const requestField = document.getElementById("decor-request");
const responseField = document.getElementById("ai-response");
const cssField = document.getElementById("theme-css");
const topField = document.getElementById("theme-html-top");
const bottomField = document.getElementById("theme-html-bottom");
const preview = document.getElementById("theme-preview");
const importMessage = document.getElementById("import-message");

function buildPrompt() {
  const event = window.partyForgeEvent || {};
  const request = requestField.value.trim() || "Create a polished, playful party theme.";
  promptField.value = `You are designing a visual theme for a self-hosted event invitation.

EVENT
Title: ${event.title || ""}
Subtitle: ${event.subtitle || ""}
Date: ${event.date || ""}
Location: ${event.location || ""}

USER'S DESIGN REQUEST
${request}

RETURN FORMAT
Return exactly these three labeled sections. Markdown fences are allowed. Do not add commentary:
=== CSS ===
\`\`\`css
your CSS
\`\`\`
=== HTML TOP ===
\`\`\`html
decorative HTML above the invitation
\`\`\`
=== HTML BOTTOM ===
\`\`\`html
decorative HTML below the invitation
\`\`\`

IMMUTABLE APP CONTRACT
The application already renders all event information, RSVP fields, guest controls, polls, potluck sign-ups, schedules, and buttons. Do not recreate, rename, hide, or replace any functional fields. You are only decorating the existing page.

Available page selectors:
body.event-page, .event-scene, .invite, .invite-hero, .invite-hero-copy, .invite-banner, .event-kicker, .event-subtitle, .event-card, .moment-card, .calendar-tile, .digital-time, .countdown, .countdown-unit, .deadline-card, .details-card, .detail, .rsvp-card, .rsvp-choices, .rsvp-choice, .notification-card, .notification-categories, .notification-opt-in, .personal-link, .party-block, .block-poll, .block-potluck, .potluck-entry, .potluck-claims, .block-schedule, .block-info, .choice-list, .timeline, .attendee-card, .avatar-list, .activity-card, .activity-list, .event-footer, button, input, textarea, select.

CSS RULES
- Write responsive CSS for both phones and desktops.
- Use gradients, borders, shadows, typography, CSS shapes, pseudo-elements, and tasteful animation.
- Keep text readable with strong contrast and large tap targets.
- Do not use @import, url(), external fonts/assets, JavaScript, position:fixed overlays, or selectors that hide functional elements.
- Avoid copyrighted characters, logos, or copied brand artwork. Evoke the requested mood with original shapes and styling.
- Keep CSS under 12,000 characters.

HTML RULES
- html_top appears before the invitation; html_bottom appears after it.
- Decorative HTML may only use div, span, p, h2, h3, strong, em, small, ul, ol, li, br, and hr.
- Only class, role, and aria-hidden attributes are permitted.
- No style attributes, links, images, forms, inputs, scripts, iframes, SVG, IDs, or event handlers.
- Decorative HTML must never pretend to be an RSVP control.
- Keep each HTML region under 3,000 characters.

Make the result distinctive and joyful without sacrificing usability.`;
}

function refreshPreview() {
  if (!preview) return;
  const css = cssField.value;
  const top = topField.value;
  const bottom = bottomField.value;
  const title = (window.partyForgeEvent && window.partyForgeEvent.title) || "Your event";
  const subtitle = (window.partyForgeEvent && window.partyForgeEvent.subtitle) || "A very good reason to get together";
  preview.srcdoc = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
  *{box-sizing:border-box}body{margin:0;font-family:system-ui;background:#ede9df;color:#17201c}.event-scene{padding:24px;min-height:100vh}.invite{max-width:620px;margin:auto;display:grid;gap:14px}.invite-hero{background:#17201c;color:white;border-radius:28px;padding:40px}.invite-hero h1{font-size:52px;line-height:.95;margin:8px 0}.event-kicker{color:#6d45ff;text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:800}.event-subtitle{opacity:.72}.event-card{background:#fffdf8;border-radius:24px;padding:24px;box-shadow:0 18px 60px rgba(0,0,0,.09)}.moment-card{display:grid;grid-template-columns:112px 1fr;gap:16px}.calendar-tile{text-align:center;border:1px solid #ddd;border-radius:18px;overflow:hidden}.calendar-tile span{display:block;background:#6d45ff;color:white;padding:6px}.calendar-tile strong{display:block;font-size:48px}.calendar-tile em{font-style:normal}.digital-time>div strong{font:700 44px monospace}.digital-time>div span{margin-left:6px;color:#6d45ff;font-weight:800}.countdown{grid-column:1/-1}.countdown-units{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.countdown-unit{background:#f1f1e9;border-radius:12px;padding:8px;text-align:center}.detail{display:grid;grid-template-columns:80px 1fr;border-bottom:1px solid #ddd;padding:10px 0}.rsvp-choices{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.rsvp-choice{padding:14px;background:#f1f1e9;border-radius:14px;text-align:center}.potluck-claims>div{display:flex;justify-content:space-between;background:#f1f1e9;border-radius:12px;padding:10px;margin-top:7px}button{border:0;border-radius:99px;background:#17201c;color:white;padding:12px 20px;font-weight:800}@media(max-width:520px){.event-scene{padding:8px}.invite-hero h1{font-size:40px}}
  ${css}</style></head><body class="event-page"><div class="event-scene">${top}<main class="invite"><header class="invite-hero"><div class="invite-hero-copy"><div class="event-kicker">Saturday · November 7</div><h1>${title}</h1><p class="event-subtitle">${subtitle}</p></div></header><section class="event-card moment-card"><div class="calendar-tile"><span>NOV</span><strong>7</strong><em>Saturday</em></div><div class="digital-time"><small>Party starts at</small><div><strong>5:00</strong><span>PM</span></div></div><div class="countdown"><small>Countdown</small><div class="countdown-units"><span class="countdown-unit"><strong>53</strong> days</span><span class="countdown-unit"><strong>04</strong> hours</span><span class="countdown-unit"><strong>18</strong> mins</span></div></div></section><section class="event-card details-card"><div class="detail"><span>Where</span><strong>Your place</strong></div></section><section class="event-card rsvp-card"><div class="event-kicker">Your invitation</div><h2>Are you in?</h2><div class="rsvp-choices"><div class="rsvp-choice">🎉 Going</div><div class="rsvp-choice">🤔 Maybe</div><div class="rsvp-choice">💌 Can't go</div></div><br><button>Save my RSVP</button></section><section class="event-card party-block block-potluck"><div class="event-kicker">Potluck</div><h2>What’s everyone bringing?</h2><div class="potluck-claims"><div><strong>Mac and cheese</strong><span>Austin</span></div><div><strong>Pumpkin pie</strong><span>Hannah</span></div></div></section></main>${bottom}</div></body></html>`;
}

if (promptButton) {
  promptButton.addEventListener("click", buildPrompt);
  buildPrompt();
}
if (document.getElementById("import-theme")) {
  document.getElementById("import-theme").addEventListener("click", () => {
    try {
      const parsed = window.PartyForgeThemeParser.parseThemeResponse(responseField.value);
      cssField.value = parsed.css;
      topField.value = parsed.html_top;
      bottomField.value = parsed.html_bottom;
      importMessage.textContent = "Theme imported. Saving now…";
      refreshPreview();
      document.getElementById("theme-form").requestSubmit();
    } catch (error) {
      importMessage.textContent = "I couldn’t find the CSS, HTML TOP, and HTML BOTTOM sections. Copy the complete AI response and try again.";
    }
  });
}
if (document.getElementById("refresh-preview")) {
  document.getElementById("refresh-preview").addEventListener("click", refreshPreview);
}
if (preview) refreshPreview();

const eventPage = document.querySelector("body.event-page");
if (eventPage) {
  if (eventPage.dataset.celebrate === "yes" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const layer = document.createElement("div");
    layer.setAttribute("aria-hidden", "true");
    Object.assign(layer.style, {position: "fixed", inset: "0", pointerEvents: "none", zIndex: "9999", overflow: "hidden"});
    document.body.appendChild(layer);
    for (let i = 0; i < 55; i++) {
      const piece = document.createElement("span");
      Object.assign(piece.style, {position: "absolute", top: "-20px", left: Math.random() * 100 + "%", width: "9px", height: "14px", background: ["#ffbe0b", "#fb5607", "#ff006e", "#8338ec", "#3a86ff"][i % 5], borderRadius: "2px"});
      layer.appendChild(piece);
      piece.animate([{transform: "translateY(0) rotate(0deg)", opacity: 1}, {transform: "translateY(" + (window.innerHeight + 40) + "px) rotate(" + (Math.random() * 900) + "deg)", opacity: 0}], {duration: 2200 + Math.random() * 1000, delay: Math.random() * 300, fill: "forwards"});
    }
    window.setTimeout(() => layer.remove(), 3800);
  }
  const countdown = eventPage.querySelector("[data-countdown]");
  if (countdown) {
    const start = Number(eventPage.dataset.eventStart);
    const days = countdown.querySelector("[data-countdown-days]");
    const hours = countdown.querySelector("[data-countdown-hours]");
    const minutes = countdown.querySelector("[data-countdown-minutes]");
    const message = countdown.querySelector("[data-countdown-message]");

    const updateCountdown = () => {
      const remaining = start - Date.now();
      if (!Number.isFinite(start)) return;
      if (remaining <= 0) {
        days.textContent = "0";
        hours.textContent = "0";
        minutes.textContent = "0";
        message.textContent = "It’s party time!";
        return;
      }
      const totalMinutes = Math.floor(remaining / 60000);
      days.textContent = String(Math.floor(totalMinutes / 1440));
      hours.textContent = String(Math.floor((totalMinutes % 1440) / 60)).padStart(2, "0");
      minutes.textContent = String(totalMinutes % 60).padStart(2, "0");
      message.textContent = "";
    };
    updateCountdown();
    window.setInterval(updateCountdown, 30000);
  }
}

function base64UrlToUint8Array(value) {
  const padding = "=".repeat((4 - value.length % 4) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

// TikTok can be blocked by a browser or a removed/private video. Never leave
// guests with an unexplained empty rectangle; the direct link stays available.
document.querySelectorAll("[data-video-preview]").forEach((card) => {
  const frame = card.querySelector("iframe");
  const status = card.querySelector("[data-video-status]");
  let ready = false;
  const unavailable = () => {
    if (ready) return;
    card.classList.add("preview-unavailable");
    status.hidden = false;
    status.textContent = "TikTok couldn’t load this preview here. Open the video using the link below.";
  };
  // Some player versions do not emit onPlayerReady. A completed iframe load
  // must also clear the timer state so a working player is never hidden.
  frame.addEventListener("load", () => {
    ready = true;
    card.classList.remove("preview-unavailable");
    status.hidden = true;
  });
  window.addEventListener("message", (event) => {
    if (event.origin !== "https://www.tiktok.com" || event.source !== frame.contentWindow || !event.data || !event.data["x-tiktok-player"]) return;
    if (event.data.type === "onPlayerReady") {
      ready = true;
      card.classList.remove("preview-unavailable");
      status.hidden = true;
    } else if (event.data.type === "onPlayerError") {
      ready = false;
      unavailable();
    }
  });
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        window.setTimeout(unavailable, 15000);
        observer.disconnect();
      }
    });
    observer.observe(card);
  } else {
    window.setTimeout(unavailable, 15000);
  }
});

document.querySelectorAll("[data-push-panel]").forEach((panel) => {
  const enableButton = panel.querySelector("[data-enable-push]");
  const disableButton = panel.querySelector("[data-disable-push]");
  const message = panel.querySelector("[data-push-message]");
  const categories = () => [...panel.querySelectorAll("input[type=checkbox]:checked")].map((input) => input.value);
  const csrf = document.body.dataset.csrf;

  const getKey = async () => {
    if (panel.dataset.vapidKey) return panel.dataset.vapidKey;
    const response = await fetch(panel.dataset.keyUrl, {credentials: "same-origin"});
    if (!response.ok) throw new Error("Could not load the notification key.");
    return (await response.json()).public_key;
  };

  const postSubscription = async (payload) => {
    const response = await fetch(panel.dataset.pushUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error("PartyForge could not save this browser.");
  };

  const isAppleMobile = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isInstalled = navigator.standalone === true ||
    (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  if (isAppleMobile && !isInstalled) {
    enableButton.textContent = "Set up iPhone / iPad notifications";
    enableButton.setAttribute("aria-expanded", "false");
    const steps = document.createElement("ol");
    steps.hidden = true;
    steps.style.lineHeight = "1.7";
    [
      "Open this same personal invitation in Safari (copy your private link if needed).",
      "Tap Share, then Add to Home Screen. If shown, keep Open as Web App turned on, then tap Add.",
      "Open the new icon on your Home Screen, tap Enable browser notifications, and choose Allow. Requires iOS or iPadOS 16.4 or later."
    ].forEach((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      steps.appendChild(item);
    });
    message.textContent = "On iPhone and iPad, notifications work from a Home Screen app. Tap the setup button for the steps. No email is needed.";
    message.after(steps);
    enableButton.addEventListener("click", () => {
      steps.hidden = false;
      enableButton.setAttribute("aria-expanded", "true");
      steps.scrollIntoView({block: "nearest"});
    });
    return;
  }

  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window) || !window.isSecureContext) {
    enableButton.disabled = true;
    enableButton.textContent = "Notifications unavailable in this browser";
    message.textContent = "Browser notifications need HTTPS and a supported browser. On iPhone or iPad, add this invitation to your Home Screen, open it there, then tap Enable.";
    return;
  }

  const registrationReady = navigator.serviceWorker.register("/sw.js").then(() => navigator.serviceWorker.ready);
  registrationReady.then(async (registration) => {
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
      const response = await fetch(panel.dataset.pushUrl + "?" + new URLSearchParams({endpoint: existing.endpoint}), {credentials: "same-origin"});
      if (!response.ok) throw new Error("Could not load notification settings.");
      const saved = await response.json();
      if (!saved.subscribed) return;
      panel.querySelectorAll("input[type=checkbox]").forEach((input) => { input.checked = saved.categories.includes(input.value); });
      message.textContent = "Notifications are on for this invitation on this browser.";
      enableButton.textContent = "Update notification choices";
      disableButton.hidden = false;
    }
  }).catch(() => {
    message.textContent = "The notification service could not start on this browser.";
  });

  enableButton.addEventListener("click", async () => {
    try {
      if (!categories().length) throw new Error("Choose at least one type of notification.");
      const permission = await Notification.requestPermission();
      if (permission !== "granted") throw new Error("Notifications were not allowed in this browser.");
      const registration = await registrationReady;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        const key = await getKey();
        subscription = await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: base64UrlToUint8Array(key)});
      }
      await postSubscription({subscription: subscription.toJSON(), categories: categories()});
      enableButton.textContent = "Update notification choices";
      disableButton.hidden = false;
      message.textContent = "Notifications are on for this browser.";
    } catch (error) {
      message.textContent = error.message;
    }
  });

  disableButton.addEventListener("click", async () => {
    try {
      const registration = await registrationReady;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await postSubscription({disabled: true, endpoint: subscription.endpoint});
        // Keep the shared browser subscription for other events and host alerts.
      }
      disableButton.hidden = true;
      enableButton.textContent = "Enable browser notifications";
      message.textContent = "Notifications are off for this invitation on this browser.";
    } catch (error) {
      message.textContent = error.message;
    }
  });
});

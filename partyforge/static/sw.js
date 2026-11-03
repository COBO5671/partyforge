self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  event.waitUntil(self.registration.showNotification(data.title || "PartyForge", {
    body: data.body || "There’s a new event update.",
    tag: data.tag || "partyforge-update",
    data: {url: data.url || "/"},
    icon: "/static/icon.svg",
    badge: "/static/icon.svg"
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(clients.matchAll({type: "window", includeUncontrolled: true}).then((windows) => {
    for (const client of windows) {
      if (client.url === target && "focus" in client) return client.focus();
    }
    return clients.openWindow ? clients.openWindow(target) : undefined;
  }));
});

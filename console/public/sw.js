// HaanJi console service worker: push notifications and a tiny offline shell.
self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => { e.waitUntil(self.clients.claim()); });
self.addEventListener("push", (e) => {
  let data = { title: "HaanJi", body: "", url: "/" };
  try { data = Object.assign(data, e.data.json()); } catch (err) {}
  e.waitUntil(self.registration.showNotification(data.title, { body: data.body, icon: "/icon-192.png", badge: "/icon-192.png", data: { url: data.url }, tag: "haanji" }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});

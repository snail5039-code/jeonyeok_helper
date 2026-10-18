// 전역도우미 서비스 워커: 기한 알림(Web Push)을 받아 보여 주고, 누르면 작전도를 연다.
// 화면 파일을 저장해 두는 오프라인 기능은 없다 (답변은 서버가 있어야 해서).

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "전역도우미", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: data.tag,
      lang: "ko",
      data: { url: data.url || "/?page=journey" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // 같은 사이트 안의 주소만 연다
  const url = new URL(event.notification.data?.url || "/", self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const open = wins.find((w) => new URL(w.url).origin === url.origin);
      if (open) return open.focus().then((w) => w.navigate(url.href));
      return self.clients.openWindow(url.href);
    }),
  );
});

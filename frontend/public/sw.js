/* Credence service worker — Web Push (E9.9 / A0.6).
 *
 * Handles `push` (show the qualified-plays notification) and `notificationclick`
 * (focus an open tab or open the dashboard). The push payload is JSON built by the
 * push-notification-sender Lambda: { title, body, url, tag }.
 */

self.addEventListener("push", (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch (e) {
    data = { title: "Credence", body: event.data ? event.data.text() : "" }
  }

  const title = data.title || "Credence"
  const options = {
    body: data.body || "",
    tag: data.tag || "credence-alert",
    icon: "/icon-dark-32x32.png",
    badge: "/icon-dark-32x32.png",
    data: { url: data.url || "/dashboard" },
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || "/dashboard"

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url)
    })
  )
})

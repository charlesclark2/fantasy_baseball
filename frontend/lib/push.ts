// Web Push helpers (E9.9 / A0.6) — register the service worker, request browser
// permission, subscribe via the VAPID public key, and hand the subscription to the
// backend. All functions are browser-only; guard on `pushSupported()` first.

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? ""

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  )
}

// VAPID public keys are base64url; the browser wants a Uint8Array applicationServerKey.
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/")
  const raw = atob(base64)
  const output = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i)
  return output
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/sw.js")
}

// Serialise a PushSubscription into the shape the backend / pywebpush expect.
function serialise(sub: PushSubscription) {
  const json = sub.toJSON()
  return {
    endpoint: json.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
    expirationTime: (sub.expirationTime as number | null) ?? null,
  }
}

export class PushPermissionDenied extends Error {}
export class PushUnsupported extends Error {}

// Full opt-in flow: register SW → request permission → subscribe → return the
// serialised subscription for the caller to POST to /alerts/subscribe.
export async function subscribeToPush(): Promise<ReturnType<typeof serialise>> {
  if (!pushSupported()) throw new PushUnsupported("Push is not supported in this browser")
  if (!VAPID_PUBLIC_KEY) throw new Error("Missing NEXT_PUBLIC_VAPID_PUBLIC_KEY")

  const permission = await Notification.requestPermission()
  if (permission !== "granted") throw new PushPermissionDenied("Notification permission denied")

  const reg = await registerServiceWorker()
  await navigator.serviceWorker.ready

  const existing = await reg.pushManager.getSubscription()
  const sub =
    existing ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    }))

  return serialise(sub)
}

// Tear down the local browser subscription (the backend row is removed via DELETE).
export async function unsubscribeFromPush(): Promise<void> {
  if (!pushSupported()) return
  const reg = await navigator.serviceWorker.getRegistration("/sw.js")
  const sub = await reg?.pushManager.getSubscription()
  if (sub) await sub.unsubscribe()
}

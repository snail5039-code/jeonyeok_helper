// 브라우저 알림(Web Push): 허락한 브라우저에 신청 기한 30·7·1일 전 알림을 보낸다.
// 서버에는 익명 ID와 이 브라우저의 푸시 구독(주소·암호화 키)만 저장된다.

import { requestJson } from "./api";

const enc = encodeURIComponent;

export type PushSupport = "ready" | "ios-install" | "unsupported";

interface Env {
  userAgent: string;
  standalone: boolean;
  hasServiceWorker: boolean;
  hasPushManager: boolean;
}

/** 이 브라우저에서 알림을 켤 수 있는지. 아이폰·아이패드는 홈 화면에 추가한 앱에서만 된다 */
export function pushSupport(env: Env): PushSupport {
  const ios = /iPad|iPhone|iPod/.test(env.userAgent);
  if (ios && !env.standalone) return "ios-install";
  return env.hasServiceWorker && env.hasPushManager ? "ready" : "unsupported";
}

export function currentEnv(): Env {
  return {
    userAgent: navigator.userAgent,
    standalone:
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true,
    hasServiceWorker: "serviceWorker" in navigator,
    hasPushManager: "PushManager" in window,
  };
}

/** VAPID 공개키(base64url)를 브라우저가 받는 바이트로 */
export function keyToBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** 서버 공개키. 없으면 알림 기능이 꺼진 서버다 */
export async function fetchPushKey(): Promise<string | null> {
  const res = await fetch("/api/push/key").catch(() => null);
  if (!res?.ok) return null;
  return (await res.json()).key ?? null;
}

export function registerWorker(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
}

/** 이 브라우저가 이미 구독 중이면 그 구독 */
export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return (await reg?.pushManager.getSubscription()) ?? null;
}

/** 서버에 이 브라우저 구독을 (다시) 알린다. 이어 하기로 익명 ID가 바뀌어도 이 ID로 옮겨진다 */
export async function saveSubscription(userId: string, sub: PushSubscription): Promise<void> {
  await requestJson("PUT", `push/${enc(userId)}`, sub.toJSON(), "알림을 켜지 못했어요.");
}

/** 알림 허락을 받고 구독한다 */
export async function turnOn(userId: string, key: string): Promise<PushSubscription> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error(
      permission === "denied"
        ? "알림이 막혀 있어요. 브라우저 주소창 왼쪽의 사이트 설정에서 알림을 허용해 주세요."
        : "알림을 허용해야 기한을 알려 드릴 수 있어요.",
    );
  }
  const reg = await registerWorker();
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyToBytes(key) }));
  await saveSubscription(userId, sub);
  return sub;
}

export async function turnOff(userId: string, sub: PushSubscription): Promise<void> {
  await requestJson("POST", `push/${enc(userId)}/unsubscribe`, { endpoint: sub.endpoint }, "알림을 끄지 못했어요.");
  await sub.unsubscribe();
}

/** 시험 알림. 받은 기기 수를 돌려준다 */
export async function sendTest(userId: string): Promise<number> {
  const res = await requestJson("POST", `push/${enc(userId)}/test`, undefined, "시험 알림을 보내지 못했어요.");
  return (await res.json()).delivered;
}

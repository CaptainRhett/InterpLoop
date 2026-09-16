<script setup>
import { onBeforeUnmount, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "./api";
import { useAuthStore } from "./stores/auth";

const auth = useAuthStore();
const router = useRouter();
let expiryTimer;
let lastRenewalAttempt = Date.now();
let expiryCheckKey = null;
const channel = typeof window.BroadcastChannel === "function"
  ? new window.BroadcastChannel("interploop-guest-session") : null;
const guestKey = () => auth.isGuest ? auth.user.guest_session_id : null;

function expireGuest() {
  if (!auth.isGuest) return;
  auth.clearSession();
  router.replace({ name: "login", query: { guest: "expired" } });
}

watch(guestKey, (key, previousKey) => {
  if (previousKey && key !== previousKey) channel?.postMessage({ type: "guest-ended", key: previousKey });
  lastRenewalAttempt = Date.now();
});

watch(() => [guestKey(), auth.user?.guest_expires_at], ([key, expiresAt]) => {
  window.clearTimeout(expiryTimer);
  if (!key || !expiresAt) return;
  channel?.postMessage({ type: "guest-renewed", key, expiresAt });
  expiryTimer = window.setTimeout(() => {
    if (guestKey() === key) return checkExpiry();
  }, Math.max(0, Date.parse(expiresAt) - Date.now()));
}, { immediate: true });

if (channel) channel.onmessage = ({ data }) => {
  if (data?.type === "guest-ended" && data.key === guestKey()) expireGuest();
  if (data?.type === "guest-renewed" && data.key === guestKey()) auth.updateGuestExpiry(data.expiresAt);
};

// Also handle expired cookies, explicit revocation, and other tabs ending a trial.
const interceptor = api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401 && error.config?.url !== "/auth/login") expireGuest();
  return Promise.reject(error);
});

async function checkExpiry() {
  if (!auth.isGuest || Date.parse(auth.user.guest_expires_at) > Date.now()) return;
  const key = guestKey();
  if (expiryCheckKey === key) return;
  expiryCheckKey = key;
  try {
    // Another tab may have renewed while this tab was suspended.
    const { data } = await api.get("/auth/me", { timeout: 10000 });
    if (guestKey() !== key) return;
    if (data.user?.guest_session_id === key && Date.parse(data.user.guest_expires_at) > Date.now()) {
      auth.updateGuestExpiry(data.user.guest_expires_at);
      return;
    }
  } catch {
    // An unverified, elapsed deadline must not leave trial data on screen.
  } finally {
    if (expiryCheckKey === key) expiryCheckKey = null;
  }
  if (guestKey() === key) expireGuest();
}

function renewOnActivity() {
  if (!auth.isGuest || auth.renewingGuest) return;
  if (Date.parse(auth.user.guest_expires_at) <= Date.now()) {
    checkExpiry();
    return;
  }
  if (Date.now() - lastRenewalAttempt < 60000) return;
  lastRenewalAttempt = Date.now();
  auth.renewGuest().catch(() => {}); // The shared banner shows renewal failures.
}
const activityEvents = ["pointerdown", "keydown", "input", "focus"];
activityEvents.forEach((name) => window.addEventListener(name, renewOnActivity));
onBeforeUnmount(() => {
  window.clearTimeout(expiryTimer);
  activityEvents.forEach((name) => window.removeEventListener(name, renewOnActivity));
  api.interceptors.response.eject(interceptor);
  channel?.close();
});
</script>

<template>
  <RouterView />
</template>

// Cloudflare Turnstile widgets. Only loaded when a site key is configured.
const SITEKEY = window.HINOVA_TURNSTILE_SITEKEY || "";
let loading = null;
const widgets = {};

function load() {
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = () => resolve(window.turnstile);
    s.onerror = () => reject(new Error("captcha"));
    document.head.appendChild(s);
  });
  return loading;
}

export const captchaEnabled = () => Boolean(SITEKEY);

export async function mount(el) {
  if (!SITEKEY || widgets[el.id] !== undefined) return;
  el.hidden = false;
  const ts = await load();
  widgets[el.id] = ts.render(el, { sitekey: SITEKEY, theme: "dark", language: "fr" });
}

export function token(el) {
  if (!SITEKEY || widgets[el.id] === undefined) return null;
  return window.turnstile.getResponse(widgets[el.id]) || null;
}

export function reset(el) {
  if (SITEKEY && widgets[el.id] !== undefined) window.turnstile.reset(widgets[el.id]);
}

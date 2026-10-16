// Transactional e-mail. Provider: Resend (HTTP API). Never logs message bodies (they hold tokens).
import { HttpError, isDev } from "./lib.js";

export async function sendEmail(env, to, subject, text) {
  if (!env.RESEND_API_KEY || !env.EMAIL_FROM) {
    if (isDev(env)) {
      console.log(`[email:dev] to=${to} subject="${subject}" (body not logged)`);
      return;
    }
    throw new HttpError(503, "EMAIL_NOT_CONFIGURED");
  }
  let ok = false;
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: env.EMAIL_FROM, to: [to], subject, text }),
    });
    ok = r.ok;
  } catch { ok = false; }
  if (!ok) throw new HttpError(502, "EMAIL_SEND_FAILED");
}

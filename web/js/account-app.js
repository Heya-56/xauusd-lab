import { api, ApiError } from "./accounts-api.js";
import * as captcha from "./captcha.js";

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (ts) => ts ? new Date(ts * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }) : "—";

const MESSAGES = {
  INVALID_EMAIL: "Adresse e-mail invalide.",
  PASSWORD_12_TO_128_CHARS: "Le mot de passe doit contenir 12 caractères minimum.",
  EMAIL_ALREADY_REGISTERED: "Un compte existe déjà avec cet e-mail. Connectez-vous.",
  INVALID_CREDENTIALS: "E-mail ou mot de passe incorrect.",
  TOO_MANY_ATTEMPTS: "Trop de tentatives. Réessayez dans 15 minutes.",
  MAX_TERMINALS_REACHED: "Limite de 3 terminaux atteinte. Révoquez-en un d'abord.",
  LABEL_1_TO_40_CHARS: "Donnez un nom au terminal (40 caractères max).",
  EMAIL_NOT_VERIFIED: "Confirmez d'abord votre adresse e-mail.",
  CAPTCHA_REQUIRED: "Validez la vérification anti-robot.",
  CAPTCHA_FAILED: "La vérification anti-robot a échoué. Réessayez.",
  CAPTCHA_NOT_CONFIGURED: "Inscription temporairement indisponible (vérification anti-robot non configurée).",
  INVALID_OR_EXPIRED_TOKEN: "Ce lien a expiré ou a déjà été utilisé. Demandez-en un nouveau.",
  INVALID_TOKEN: "Lien invalide.",
  WAIT_BEFORE_RESEND: "Patientez une minute avant de renvoyer l'e-mail.",
  API_NOT_CONFIGURED: "Service de comptes non configuré pour cet environnement.",
  NETWORK_ERROR: "Connexion impossible. Vérifiez votre réseau.",
};
const msg = (e) => MESSAGES[e?.code] || "Une erreur est survenue. Réessayez.";
const VIEWS = ["auth-view", "forgot-view", "reset-view", "account-view"];

let mode = "login";

function show(view) {
  VIEWS.forEach((v) => { $(v).hidden = v !== view; });
  if (view !== "account-view") $("account-badges").innerHTML = "";
}

function flash(text) {
  $("flash").textContent = text;
  $("flash").hidden = !text;
}

function setMode(next) {
  mode = next;
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  $("t-auth").textContent = mode === "login" ? "Connexion" : "Créer un compte";
  $("auth-submit").textContent = mode === "login" ? "Se connecter" : "Démarrer l'essai gratuit";
  $("trial-note").hidden = mode === "login";
  $("pw-hint").hidden = mode === "login";
  $("forgot-open").hidden = mode !== "login";
  $("auth-form").password.autocomplete = mode === "login" ? "current-password" : "new-password";
  $("auth-error").textContent = "";
  if (mode === "signup") captcha.mount($("captcha-signup")).catch(() => {});
  else $("captcha-signup").hidden = true;
}

async function showAccount() {
  const me = await api.me();
  show("account-view");
  const planLabel = { trial: "Essai gratuit", subscription: "Abonnement", white_label: "Licence white-label", none: "Aucun" }[me.plan] || me.plan;
  $("account-badges").innerHTML = `<span class="badge" data-tone="accent">${esc(planLabel)}</span><span class="badge" data-tone="warn">Live désactivé</span>`;
  $("plan").innerHTML = `<dt>Compte</dt><dd>${esc(me.email)}</dd><dt>E-mail</dt><dd>${me.email_verified ? "confirmé" : "à confirmer"}</dd>
    <dt>Formule</dt><dd>${esc(planLabel)}</dd><dt>Fin</dt><dd>${fmt(me.plan_ends_at)}</dd><dt>Trading réel</dt><dd>désactivé</dd>`;
  $("verify-banner").hidden = me.email_verified;
  $("term-form").querySelectorAll("input,button").forEach((el) => { el.disabled = !me.email_verified; });
  if (api.base) $("api-origin").textContent = new URL(api.base).origin;
  await renderTerminals();
}

async function renderTerminals() {
  const { terminals, max } = await api.terminals();
  $("term-count").textContent = `${terminals.length} / ${max}`;
  $("terminals").innerHTML = terminals.length ? terminals.map((t) => `
    <li class="strategy" data-on="true">
      <span class="strategy-name">${esc(t.label)}</span>
      <button class="btn btn-small" type="button" data-revoke="${esc(t.terminal_id)}">Révoquer</button>
      <span class="strategy-sub">clé ${esc(t.key_prefix)}… · créé le ${fmt(t.created_at)} · ${t.last_seen_at ? "vu le " + fmt(t.last_seen_at) : "jamais connecté"}</span>
    </li>`).join("") : `<li class="empty">Aucun terminal connecté.</li>`;
}

async function handleLinks() {
  const params = new URLSearchParams(location.search);
  const verify = params.get("verify"), reset = params.get("reset");
  if (verify || reset) history.replaceState(null, "", location.pathname);   // tokens never stay in the address bar
  if (verify) {
    try { await api.verify(verify); flash("Adresse e-mail confirmée. Vous pouvez connecter un terminal MT5."); }
    catch (err) { flash(msg(err)); }
  }
  if (reset) {
    show("reset-view");
    $("reset-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const pw = e.target.password.value;
      if (pw.length < 12) { $("reset-error").textContent = MESSAGES.PASSWORD_12_TO_128_CHARS; return; }
      try {
        await api.reset(reset, pw);
        e.target.reset();
        flash("Mot de passe mis à jour. Connectez-vous avec le nouveau mot de passe.");
        setMode("login");
        show("auth-view");
      } catch (err) { $("reset-error").textContent = msg(err); }
    });
    return true;
  }
  return false;
}

async function init() {
  document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  $("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, email = f.email.value.trim(), pw = f.password.value;
    $("auth-error").textContent = "";
    if (!email || !f.email.checkValidity()) { $("auth-error").textContent = MESSAGES.INVALID_EMAIL; return; }
    if (mode === "signup" && pw.length < 12) { $("auth-error").textContent = MESSAGES.PASSWORD_12_TO_128_CHARS; return; }
    if (!pw) { $("auth-error").textContent = "Saisissez votre mot de passe."; return; }
    const token = mode === "signup" ? captcha.token($("captcha-signup")) : null;
    if (mode === "signup" && captcha.captchaEnabled() && !token) { $("auth-error").textContent = MESSAGES.CAPTCHA_REQUIRED; return; }
    $("auth-submit").disabled = true;
    try {
      const r = await (mode === "login" ? api.login(email, pw) : api.signup(email, pw, token));
      f.reset();
      if (mode === "signup") flash(r.email_verification === "sent"
        ? `Compte créé. Un e-mail de confirmation a été envoyé à ${email}.`
        : "Compte créé, mais l'e-mail de confirmation n'a pas pu partir. Utilisez « Renvoyer l'e-mail ».");
      await showAccount();
    } catch (err) {
      $("auth-error").textContent = msg(err);
      captcha.reset($("captcha-signup"));
    } finally { $("auth-submit").disabled = false; }
  });
  $("auth-form").addEventListener("input", () => { $("auth-error").textContent = ""; });

  $("forgot-open").addEventListener("click", () => { show("forgot-view"); captcha.mount($("captcha-forgot")).catch(() => {}); });
  document.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => { show("auth-view"); setMode("login"); }));
  $("forgot-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("forgot-error").textContent = "";
    const email = e.target.email.value.trim();
    if (!email || !e.target.email.checkValidity()) { $("forgot-error").textContent = MESSAGES.INVALID_EMAIL; return; }
    const token = captcha.token($("captcha-forgot"));
    if (captcha.captchaEnabled() && !token) { $("forgot-error").textContent = MESSAGES.CAPTCHA_REQUIRED; return; }
    try { await api.forgot(email, token); $("forgot-ok").hidden = false; }
    catch (err) { $("forgot-error").textContent = msg(err); captcha.reset($("captcha-forgot")); }
  });
  $("forgot-form").addEventListener("input", () => { $("forgot-error").textContent = ""; });

  $("verify-resend").addEventListener("click", async () => {
    $("verify-error").textContent = "";
    try { await api.resendVerification(); flash("E-mail de confirmation renvoyé."); }
    catch (err) { $("verify-error").textContent = msg(err); }
  });

  $("logout").addEventListener("click", async () => { try { await api.logout(); } finally { show("auth-view"); setMode("login"); } });
  $("term-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("term-error").textContent = "";
    const label = e.target.label.value.trim();
    if (!label) { $("term-error").textContent = MESSAGES.LABEL_1_TO_40_CHARS; return; }
    try {
      const t = await api.createTerminal(label);
      e.target.reset();
      $("key-value").textContent = t.api_key;
      $("key-reveal").hidden = false;
      await renderTerminals();
    } catch (err) { $("term-error").textContent = msg(err); }
  });
  $("term-form").addEventListener("input", () => { $("term-error").textContent = ""; });
  $("key-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("key-value").textContent); $("key-copy").textContent = "Copiée"; } catch { /* manual copy */ }
  });
  $("terminals").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-revoke]");
    if (!b || !confirm("Révoquer ce terminal ? Son EA ne pourra plus recevoir de signaux.")) return;
    try { await api.revokeTerminal(b.dataset.revoke); $("key-reveal").hidden = true; await renderTerminals(); }
    catch (err) { $("term-error").textContent = msg(err); }
  });

  setMode("login");
  if (await handleLinks()) return;
  try { await showAccount(); }
  catch (err) {
    show("auth-view");
    if (err instanceof ApiError && err.status === 0) $("auth-error").textContent = msg(err);
  }
}

init();

import { api, ApiError } from "./accounts-api.js";

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
  API_NOT_CONFIGURED: "Service de comptes non configuré pour cet environnement.",
  NETWORK_ERROR: "Connexion impossible. Vérifiez votre réseau.",
};
const msg = (e) => MESSAGES[e?.code] || "Une erreur est survenue. Réessayez.";

let mode = "login";

function setMode(next) {
  mode = next;
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  $("t-auth").textContent = mode === "login" ? "Connexion" : "Créer un compte";
  $("auth-submit").textContent = mode === "login" ? "Se connecter" : "Démarrer l'essai gratuit";
  $("trial-note").hidden = mode === "login";
  $("pw-hint").hidden = mode === "login";
  $("auth-form").password.autocomplete = mode === "login" ? "current-password" : "new-password";
  $("auth-error").textContent = "";
}

async function showAccount() {
  const me = await api.me();
  $("auth-view").hidden = true;
  $("account-view").hidden = false;
  const planLabel = { trial: "Essai gratuit", subscription: "Abonnement", white_label: "Licence white-label", none: "Aucun" }[me.plan] || me.plan;
  $("account-badges").innerHTML = `<span class="badge" data-tone="accent">${esc(planLabel)}</span><span class="badge" data-tone="warn">Live désactivé</span>`;
  $("plan").innerHTML = `<dt>Compte</dt><dd>${esc(me.email)}</dd><dt>Formule</dt><dd>${esc(planLabel)}</dd>
    <dt>Fin</dt><dd>${fmt(me.plan_ends_at)}</dd><dt>Trading réel</dt><dd>désactivé</dd>`;
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

function showAuth() {
  $("account-view").hidden = true;
  $("auth-view").hidden = false;
  $("account-badges").innerHTML = "";
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
    $("auth-submit").disabled = true;
    try {
      await (mode === "login" ? api.login(email, pw) : api.signup(email, pw));
      f.reset();
      await showAccount();
    } catch (err) { $("auth-error").textContent = msg(err); }
    finally { $("auth-submit").disabled = false; }
  });
  $("auth-form").addEventListener("input", () => { $("auth-error").textContent = ""; });
  $("logout").addEventListener("click", async () => { try { await api.logout(); } finally { showAuth(); } });
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
  try { await showAccount(); }
  catch (err) {
    showAuth();
    if (err instanceof ApiError && err.status === 0) $("auth-error").textContent = msg(err);
  }
}

init();

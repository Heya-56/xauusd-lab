import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../web/js/kernel-console.js", import.meta.url), "utf8");
const html = await readFile(new URL("../web/kernel.html", import.meta.url), "utf8");

test("kernel console page exposes safe diagnostics and no order submission route", () => {
  assert.match(html, /Kernel Test Bench/);
  assert.match(html, /NO LIVE ORDERS/);
  assert.match(html, /run-suite/);
  assert.doesNotMatch(source, /\/v1\/ea\/signal/);
  assert.doesNotMatch(source, /\/v1\/config/);
});

test("event console contract lists only the declared research event types", () => {
  for (const type of ["market.tick", "market.bar_closed", "strategy.signal", "risk.decision", "research.result", "system.health"]) {
    assert.ok(source.includes(type), "missing event type: " + type);
  }
  assert.match(source, /trade\.execute/);
  assert.match(source, /execution_allowed===true/);
});

test("console clearly distinguishes browser checks from real Python kernel execution", () => {
  assert.match(html, /ne prétend pas exécuter le moteur Python depuis le navigateur/);
  assert.match(html, /aucun endpoint public de test du kernel n’est défini/);
});

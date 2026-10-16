// Minimal Cloudflare D1 API over node:sqlite, applying the repo's real migrations.
import { DatabaseSync } from "node:sqlite";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export function makeD1(migrationsDir) {
  const db = new DatabaseSync(":memory:");
  for (const f of readdirSync(migrationsDir).filter((x) => x.endsWith(".sql")).sort()) {
    db.exec(readFileSync(join(migrationsDir, f), "utf8"));
  }
  const stmt = (sql, args = []) => ({
    sql, args,
    bind: (...a) => stmt(sql, a),
    first: async () => db.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: db.prepare(sql).all(...args) }),
    run: async () => { const r = db.prepare(sql).run(...args); return { meta: { changes: Number(r.changes) } }; },
  });
  return {
    raw: db,
    prepare: (sql) => stmt(sql),
    batch: async (stmts) => {
      db.exec("BEGIN");
      try { for (const s of stmts) db.prepare(s.sql).run(...s.args); db.exec("COMMIT"); }
      catch (e) { db.exec("ROLLBACK"); throw e; }
      return stmts.map(() => ({ success: true }));
    },
  };
}

import { json } from "../apiHarness";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Product-demo tour shares/knowledge/memory fixtures. */
export function handleDemoDataFixture(req: any, ctx: PlatformFixtureContext) {
  const { options, demoShares, demoKnowledge, demoKnowledgeCategories, demoMemory } = ctx;
      // ── Server-detail demo data (sharing / notes / AI memory) ──────────────
      // Only served for the product-demo tour so regular tests keep empty tabs.
      if (options.demoData) {
        const sharesMatch = req.path.match(/^\/servers\/api\/(\d+)\/shares\/$/);
        if (sharesMatch && req.method === "GET") {
          return json({ success: true, shares: demoShares });
        }

        const createShareMatch = req.path.match(/^\/servers\/api\/(\d+)\/share\/$/);
        if (createShareMatch && req.method === "POST") {
          const rawUser = String(req.body?.user || "").trim() || "new.user";
          demoShares.push({
            id: 900 + demoShares.length,
            user_id: 90 + demoShares.length,
            username: rawUser,
            email: rawUser.includes("@") ? rawUser : `${rawUser}@corp.io`,
            share_context: req.body?.share_context !== false,
            can_connect_terminal: req.body?.can_connect_terminal !== false,
            can_execute_command: false,
            can_read_files: true,
            can_write_files: false,
            expires_at: req.body?.expires_at ?? null,
            created_at: "2026-03-01T08:00:00.000Z",
            is_active: true,
          });
          return json({ success: true });
        }

        const revokeShareMatch = req.path.match(/^\/servers\/api\/(\d+)\/shares\/(\d+)\/revoke\/$/);
        if (revokeShareMatch && req.method === "POST") {
          const shareId = Number(revokeShareMatch[2]);
          const idx = demoShares.findIndex((share) => share.id === shareId);
          if (idx >= 0) demoShares.splice(idx, 1);
          return json({ success: true });
        }

        const knowledgeMatch = req.path.match(/^\/servers\/api\/(\d+)\/knowledge\/$/);
        if (knowledgeMatch && req.method === "GET") {
          return json({ success: true, items: demoKnowledge, categories: demoKnowledgeCategories });
        }

        const memoryMatch = req.path.match(/^\/servers\/api\/(\d+)\/memory\/snapshots\/$/);
        if (memoryMatch && req.method === "GET") {
          return json({ success: true, items: demoMemory });
        }
      }
  return undefined;
}

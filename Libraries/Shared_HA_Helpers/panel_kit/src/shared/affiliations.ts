/**
 * Shared affiliation catalog helpers for Game Master, Registration + GBN panels.
 *
 * Ownership: Game Master owns catalog CRUD (categories + choices).
 * Registration attaches/removes player tags; GBN is select-only.
 * Catalog is read via WS game_master/get_affiliation_catalog.
 *
 * Central model: Event → affiliation category → affiliation choice.
 * Allegiance / Faction are category *names*, not separate types.
 */

export type AffChoice = { id: string; name: string };

export type AffCategory = {
  id: string;
  name: string;
  affiliations: AffChoice[];
};

export type AffCatalog = {
  event_id: string | null;
  categories: AffCategory[];
};

export type PlayerAffiliation = {
  category_id?: string;
  category_name?: string;
  affiliation_id?: string;
  affiliation_name?: string;
};

const KNOWN_NEOCORP_SLUGS = new Set([
  "reboot",
  "helix",
  "endline",
  "freelancer",
]);

export function emptyCatalog(): AffCatalog {
  return { event_id: null, categories: [] };
}

export function filterChoices(choices: AffChoice[], query: string): AffChoice[] {
  const q = (query || "").trim().toLowerCase();
  if (!q) return choices;
  return choices.filter((c) => (c.name || "").toLowerCase().includes(q));
}

export function findChoiceExact(
  choices: AffChoice[],
  name: string
): AffChoice | undefined {
  const needle = (name || "").trim().toLowerCase();
  if (!needle) return undefined;
  return choices.find((c) => (c.name || "").trim().toLowerCase() === needle);
}

export function playerAssignmentForCategory(
  affiliations: PlayerAffiliation[] | undefined,
  category: AffCategory
): string {
  if (!affiliations?.length) return "";
  const catId = category.id;
  const catName = (category.name || "").trim().toLowerCase();
  for (const row of affiliations) {
    if (row.category_id && String(row.category_id) === String(catId)) {
      return (row.affiliation_name || "").trim();
    }
    if (
      catName &&
      (row.category_name || "").trim().toLowerCase() === catName
    ) {
      return (row.affiliation_name || "").trim();
    }
  }
  return "";
}

export function affiliationsSummary(
  affiliations: PlayerAffiliation[] | undefined
): string {
  if (!affiliations?.length) return "—";
  return affiliations
    .map((a) => {
      const cat = (a.category_name || "").trim() || "Category";
      const name = (a.affiliation_name || "").trim() || "?";
      return `${cat}: ${name}`;
    })
    .join(" · ");
}

/** Map Allegiance-like display names to logo slug when known. */
export function neocorpSlugFromName(name: string): string {
  const raw = (name || "").trim();
  if (!raw) return "";
  const lower = raw.toLowerCase();
  if (KNOWN_NEOCORP_SLUGS.has(lower)) return lower;
  const first = lower.split(/\s+/)[0] || "";
  if (KNOWN_NEOCORP_SLUGS.has(first)) return first;
  return lower;
}

export function isAllegianceCategory(name: string): boolean {
  const n = (name || "").trim().toLowerCase();
  return n === "allegiance" || n === "neocorp";
}

export function isFactionCategory(name: string): boolean {
  return (name || "").trim().toLowerCase() === "faction";
}

/**
 * Build Central affiliations map from category → selected choice id.
 * Empty selection omits the key (create) or can pass nulls via clearIds.
 */
export function buildAffiliationsPayload(
  categories: AffCategory[],
  selectedByCategoryId: Record<string, string>,
  opts?: { previousByCategoryId?: Record<string, string> }
): Record<string, string | null> {
  const previousByCategoryId = opts?.previousByCategoryId;
  const out: Record<string, string | null> = {};
  for (const cat of categories) {
    const chosenName = (selectedByCategoryId[cat.id] || "").trim();
    const match = findChoiceExact(cat.affiliations || [], chosenName);
    const prev = previousByCategoryId?.[cat.id];
    if (match) {
      out[cat.id] = match.id;
    } else if (prev && !chosenName) {
      out[cat.id] = null;
    }
  }
  return out;
}

/**
 * Create a choice via Game Master and return it from the refreshed catalog.
 * Registration/GBN panels no longer call this (select-only); kept for
 * Game Master-owned flows.
 */
export async function ensureAffiliationChoice(
  hass: {
    callService: (
      domain: string,
      service: string,
      data?: Record<string, unknown>
    ) => Promise<unknown>;
    callWS: <T>(msg: Record<string, unknown>) => Promise<T>;
  },
  categoryId: string,
  name: string
): Promise<AffChoice | null> {
  const cleaned = (name || "").trim();
  if (!cleaned || !categoryId) return null;
  await hass.callService("game_master", "create_affiliation", {
    category_id: categoryId,
    name: cleaned,
  });
  const catalog = await hass.callWS<AffCatalog>({
    type: "game_master/get_affiliation_catalog",
  });
  const cat = (catalog.categories || []).find(
    (c) => String(c.id) === String(categoryId)
  );
  return findChoiceExact(cat?.affiliations || [], cleaned) || null;
}

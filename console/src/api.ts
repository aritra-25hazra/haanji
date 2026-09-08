import type {
  ConversationDetail, ConversationSummary, Dashboard, LexiconEntry, Verification,
} from "./types";
import * as mock from "./mock";

/**
 * One place that knows how to reach the Core API.
 *
 * The console runs against real data when a token is present and against the
 * fixtures in mock.ts otherwise. That is not a toy mode: it is how the
 * interface gets designed and reviewed without a database, and how the
 * screenshots in the report were produced.
 */
const BASE = "/api/v1";

function token(): string | null {
  return localStorage.getItem("haanji.token");
}

export function isOffline(): boolean {
  return token() === null;
}

async function get<T>(path: string, fallback: () => T): Promise<T> {
  if (isOffline()) {
    return new Promise((resolve) => setTimeout(() => resolve(fallback()), 120));
  }
  const response = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${token()}` },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const api = {
  dashboard: () => get<Dashboard>("/analytics/dashboard", mock.dashboard),
  conversations: () => get<ConversationSummary[]>("/conversations", mock.conversations),
  conversation: (id: string) =>
    get<ConversationDetail>(`/conversations/${id}`, () => mock.conversation(id)),
  receiptsVerify: () => get<Verification>("/receipts/verify", mock.verification),
  lexicon: () => get<LexiconEntry[]>("/lexicon", mock.lexicon),
  packs: () => get<string[]>("/packs", mock.packs),
};

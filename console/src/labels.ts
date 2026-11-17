/** The words owner screens use, in one place, so the dashboard, its legend,
 *  the calls list and the call page always agree. */
import PACKS from "./packs.json";

export const OUTCOME_LABEL: Record<string, string> = {
  BOOKED: "Booking hui", RESCHEDULED: "Time badla", FAQ_ANSWERED: "Jawab diya", LEAD_CAPTURED: "Callback chahiye",
  HANDED_OFF: "Insaan ko diya", REFUSED: "Mana kiya", ABANDONED: "Beech mein kati", IN_PROGRESS: "Chal rahi hai",
};
export const OUTCOME_HINT: Record<string, string> = {
  REFUSED: "Agent ne ek sawaal ka jawab dene se mana kiya (jaise dawai ya discount); call aage chalti rahi.",
  HANDED_OFF: "Agent ne call staff ko di: emergency, shikayat, ya caller ne insaan maanga.",
  LEAD_CAPTURED: "Kaam call par nahi ho paaya; number note hua, aapko wapas call karna hai.",
  ABANDONED: "Caller ne booking ya jawab se pehle call chhod di.",
};
export const outcomeLabel = (o: string | null) => OUTCOME_LABEL[o || "IN_PROGRESS"] ?? (o ?? "").replace(/_/g, " ").toLowerCase();

const NAMES = new Map((PACKS as { packs: { pack_id: string; business_name: string; display_name: string }[] }).packs
  .map((p) => [p.pack_id, p] as const));
/** "Smile Care Dental", not "dental_clinic". A pack made in Nayi dukaan is not in the file: its id, spaced. */
export const businessName = (pack: string) => NAMES.get(pack)?.business_name ?? pack.replace(/_/g, " ");
export const packLabel = (pack: string) => {
  const p = NAMES.get(pack);
  return p ? `${p.business_name} · ${p.display_name}` : pack.replace(/_/g, " ");
};

/** Meta's sandbox numbers are +1 555 …; never call one "asli". */
export const isTestNumber = (n?: string | null) => !!n && /^\+?1[\s(]*555/.test(n.replace(/[^\d+(]/g, "").replace(/\(/g, ""));

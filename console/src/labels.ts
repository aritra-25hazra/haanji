/** The words owner screens use, in one place, so the dashboard, its legend,
 *  the calls list and the call page always agree. */
import PACKS from "./packs.json";
import { en, t } from "./i18n";

export const OUTCOME_LABEL: Record<string, string> = {
  BOOKED: en("Booked"), RESCHEDULED: en("Rescheduled"), FAQ_ANSWERED: en("Answered"), LEAD_CAPTURED: en("Needs a callback"),
  HANDED_OFF: en("Passed to staff"), REFUSED: en("Declined"), ABANDONED: en("Caller hung up"), IN_PROGRESS: en("In progress"),
};
export const OUTCOME_HINT: Record<string, string> = {
  REFUSED: en("The agent declined one question (such as medicine or a discount); the call went on."),
  HANDED_OFF: en("The agent passed the call to staff: an emergency, a complaint, or the caller asked for a person."),
  LEAD_CAPTURED: en("The call could not finish the job; the number is noted and you need to call back."),
  ABANDONED: en("The caller left before a booking or an answer."),
};
export const outcomeLabel = (o: string | null) => {
  const l = OUTCOME_LABEL[o || "IN_PROGRESS"];
  return l ? t(l) : (o ?? "").replace(/_/g, " ").toLowerCase();
};

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

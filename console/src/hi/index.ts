// Hindi (Roman-script Hinglish) for every English UI string, keyed by the
// English. One file per area so they can be edited without stepping on each other.
import common from "./common";
import engine from "./engine";
import home from "./home";
import owner from "./owner";

export const HI: Record<string, string> = { ...common, ...owner, ...engine, ...home };

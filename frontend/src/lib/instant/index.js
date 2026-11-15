import { calculate } from "./calc.js";
import { convertUnits } from "./units.js";

/** Instant answers computed in the browser (work the same with or without a backend). */
export function instantAnswer(query) {
  return convertUnits(query) || calculate(query);
}

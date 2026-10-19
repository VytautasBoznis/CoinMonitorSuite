// Our re-implementation of the upstream schedule helpers (same output shapes and semantics).
import { normalizeTime } from "../utils/time";

export const manualStep = (start: any, stepDuration: any, steps: number, amount: number,
                           dateFormat?: string) => ({
  type: "step", start: normalizeTime(start, dateFormat),
  stepDuration: normalizeTime(stepDuration, dateFormat), steps, amount,
});

export const manualCliff = (start: any, amount: number, dateFormat?: string) => ({
  type: "cliff", start: normalizeTime(start, dateFormat), amount,
});

export const manualLinear = (start: any, end: any, amount: number, dateFormat?: string) => ({
  type: "linear", start: normalizeTime(start, dateFormat), end: normalizeTime(end, dateFormat),
  amount,
});

export const manualLog = (start: any, end: any, amount: number, periodLength: number,
                          percentDecreasePerPeriod: number, converging = true,
                          percentInFirstPeriod?: number, dateFormat?: string) => {
  let sections: any[] = [];
  let thisStart: number = normalizeTime(start, dateFormat);
  const periods = (normalizeTime(end, dateFormat) - thisStart) / periodLength;
  let workingQty = 100;
  let sum = 0;
  for (let i = 1; i < periods; i++) {
    const thisQty = percentInFirstPeriod && i == 1
      ? amount * (percentInFirstPeriod / 100)
      : workingQty * (1 - percentDecreasePerPeriod / 100);
    sections.push(manualLinear(thisStart, thisStart + periodLength, thisQty));
    sum += thisQty;
    workingQty = thisQty;
    thisStart += periodLength;
  }
  if (converging) {
    const factor = amount / sum;
    sections = sections.map((s) => ({ ...s, amount: s.amount * factor }));
  }
  return sections;
};

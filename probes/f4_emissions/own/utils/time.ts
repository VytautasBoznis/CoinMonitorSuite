// Our re-implementation of the upstream time helpers the schedules use (no dayjs).
export const periodToSeconds: any = {
  year: 31556926,
  month: 2629743,
  week: 604800,
  day: 86400,
  hour: 3600,
  minute: 60,
  months: (n: number) => periodToSeconds.month * n,
  weeks: (n: number) => periodToSeconds.week * n,
  years: (n: number) => periodToSeconds.year * n,
  days: (n: number) => periodToSeconds.day * n,
};

export const months = (start: number, n: number) =>
  Math.round((start + periodToSeconds.months(n)) / 86400) * 86400;
export const years = (start: number, n: number) =>
  Math.round((start + periodToSeconds.years(n)) / 86400) * 86400;

export function readableToSeconds(readableDate: string): number {
  return Math.floor(new Date(readableDate).getTime() / 1000);
}

// Pinned "now" so a run is reproducible: the upstream helper returns the wall clock.
export function unixTimestampNow(): number {
  return 1790812800; // 2026-10-01
}

function parseDateString(input: string, format: string, key: string) {
  const result = input.substring(format.indexOf(key), format.lastIndexOf(key) + 1);
  if (["d", "m"].includes(key) && result.length == 1) return `0${result}`;
  if (key == "y" && result.length == 2) return `20${result}`;
  return result;
}

export function stringToTimestamp(inputDate: string, format = "YYYY/MM/DD"): number {
  const f = format.toLowerCase();
  const s = readableToSeconds(
    `${parseDateString(inputDate, f, "y")}-${parseDateString(inputDate, f, "m")}-` +
    `${parseDateString(inputDate, f, "d")}T00:00:00.000Z`);
  if (isNaN(s)) throw new Error(`${inputDate} is not in the format ${format}`);
  return s;
}

export function normalizeTime(time: string | number, format?: string): number {
  if (typeof time != "string") return time;
  if (time.search(/([/-])/g) == -1 && time.length == 10) return parseInt(time);
  return stringToTimestamp(time, format ?? "YYYY/MM/DD");
}

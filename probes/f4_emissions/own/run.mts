// Evaluate every staged protocol offline and dump its schedule sections as JSON.
import { readdirSync, writeFileSync } from "fs";

// Some files fire async calls into our stubs that nobody awaits; their failures must not kill the run.
process.on("unhandledRejection", () => {});
process.on("uncaughtException", () => {});

const KINDS = ["cliff", "step", "linear"];
const NOT_SECTIONS = new Set(["meta", "categories", "documented"]);

async function resolve(v: any): Promise<any> {
  try {
    if (typeof v === "function") v = v(false);
    v = await v;
    const out: any[] = [];
    for (let x of (Array.isArray(v) ? v : [v]).flat(5)) {
      x = await x;
      if (typeof x === "function") x = await x(false);
      out.push(...(Array.isArray(x) ? x.flat(5) : [x]));
    }
    return out.length && out.every((x) => x && KINDS.includes(x.type)) ? out : "unsupported";
  } catch {
    return "unsupported";
  }
}

const dir = "/w/protocols";
const result: any = {};
for (const f of readdirSync(dir).filter((f) => f.endsWith(".ts")).sort()) {
  try {
    const m = await import(`${dir}/${f}`);
    const p = m.default?.default ?? m.default; // CommonJS-compiled .ts nests the default
    const sections: any = {};
    for (const [k, v] of Object.entries(p)) {
      if (!NOT_SECTIONS.has(k)) sections[k] = await resolve(v);
    }
    result[f] = { meta: JSON.parse(JSON.stringify(p.meta ?? {})),
                  categories: p.categories ?? null, sections };
  } catch (e) {
    result[f] = { error: String(e).slice(0, 300) };
  }
}
writeFileSync("/w/schedules.json", JSON.stringify(result));
console.log(`evaluated ${Object.keys(result).length} files`);

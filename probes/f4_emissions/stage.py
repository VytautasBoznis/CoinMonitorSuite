"""Stage DefiLlama's token-unlock schedules for a sandboxed, offline run (input to idea 4, F4).

SOURCE. DefiLlama's `emissions-adapters` repo (one TypeScript file per protocol, unlock schedules
as `manualCliff` / `manualStep` / `manualLinear` calls) is no longer public and its API is paid.
A copy survives at github.com/Omni-Chain-Protocols/emissions-adapters, branch
FelixBruguera-patch-1, commit fa7d0a0 (2026-03-21, a DefiLlama maintainer's commit), no license
file.
Unknown publisher, so its code is treated as untrusted.

WHAT THIS DOES. Copies protocols/*.ts from the checkout into a work dir and replaces every module
they import with our code: re-implementations of the pure schedule helpers (own/adapters/manual.ts,
own/utils/time.ts, same semantics as upstream) and stubs for everything that would touch a chain,
an API or npm, returning an "unsupported" marker. Files importing npm packages are dropped. Nothing
from the checkout but protocols/ runs, and it runs offline in a container:

  curl -L -o repo.tgz https://codeload.github.com/Omni-Chain-Protocols/emissions-adapters/tar.gz/fa7d0a0a95415857ba898596a4ae75b38b7753bf
  tar xzf repo.tgz -C <new empty dir>
  python -I probes/f4_emissions/stage.py <checkout dir> <work dir>
  docker run --rm -v <work dir>:/w -w /w node:22-alpine sh -c "npm init -y && npm i tsx@4"
  docker run --rm --network none -v <work dir>:/w -w /w node:22-alpine npx tsx run.mts
  -> <work dir>/schedules.json, read by probes/f4_unlock_events.py

usage: python -I stage.py <checkout dir> <work dir>
"""
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

src, out = Path(sys.argv[1]), Path(sys.argv[2])
IMPORT = re.compile(r'import\s+(type\s+)?(.*?)\s+from\s+"([^"]+)"', re.S)
OWN = {"adapters/manual", "utils/time"}

if out.exists():
    shutil.rmtree(out)
(out / "protocols").mkdir(parents=True)

names = defaultdict(set)  # module (repo-relative, no ext) -> imported names
defaults = set()
skipped = []
for f in sorted((src / "protocols").glob("*.ts")):
    text = f.read_text(encoding="utf-8")
    specs = IMPORT.findall(text)
    if any(not s.startswith(".") for _, _, s in specs):
        skipped.append(f.name)
        continue
    for _is_type, clause, spec in specs:
        mod = str(PurePosixPath("protocols", spec).as_posix())
        parts = []
        for p in PurePosixPath(mod).parts:
            if p == "..":
                parts.pop()
            elif p != ".":
                parts.append(p)
        mod = "/".join(parts)
        if mod.startswith("protocols/"):
            continue
        clause = clause.strip()
        if clause.startswith("* as"):
            continue
        braces = re.search(r"\{(.*)\}", clause, re.S)
        if braces:
            for n in braces.group(1).split(","):
                n = n.strip().removeprefix("type ").split(" as ")[0].strip()
                if n:
                    names[mod].add(n)
        head = clause.split("{")[0].strip().rstrip(",").strip()
        if head:
            defaults.add(mod)
    shutil.copy(f, out / "protocols" / f.name)

for mod in sorted(set(names) | defaults):
    if mod in OWN:
        continue
    lines = ['const U = (..._a: any[]): any => ({ type: "unsupported" });']
    lines += [f"export const {n}: any = U;" for n in sorted(names[mod])]
    lines.append("export default U;")
    p = out / (mod + ".ts")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

own = Path(__file__).parent / "own"
shutil.copy(own / "run.mts", out / "run.mts")
for mod in OWN:
    real = (own / (mod + ".ts")).read_text(encoding="utf-8")
    have = set(re.findall(r"export (?:const|function) (\w+)", real))
    extra = sorted(names[mod] - have)
    stubs = "".join(f'export const {n}: any = (..._a: any[]): any => ({{ type: "unsupported" }});\n'
                    for n in extra)
    p = out / (mod + ".ts")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(real + stubs, encoding="utf-8")
    print(f"{mod}: imported names without a real implementation -> stubbed: {extra}")
print(f"copied {len(list((out / 'protocols').glob('*.ts')))} protocol files;"
      f" skipped (npm imports) {len(skipped)}: {skipped}")
print("stubbed modules:", sorted(m for m in set(names) | defaults if m not in OWN))

#!/usr/bin/env python3
"""
Generate static Markdown documentation from the deterministic catalog.

Output: a single Markdown file with sections per device and operation, listing:
- parameters (with inferred type/default/range if available)
- container requirements
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict


def load_catalog(path: Path) -> Dict:
    if not path.exists():
        raise SystemExit(f"Catalog not found: {path}")
    return json.loads(path.read_text())


def fmt_param(name: str, meta: Dict) -> str:
    parts = [f"`{name}`"]
    if meta:
        if meta.get("type"):
            parts.append(f"(type: {meta['type']})")
        if meta.get("default") is not None:
            parts.append(f"default: `{meta['default']}`")
        if "min" in meta and "max" in meta:
            parts.append(f"range: `{meta['min']}` – `{meta['max']}`")
    return " ".join(parts)


def generate_md(catalog: Dict) -> str:
    lines = []
    lines.append("# Momentum Step Reference\n")
    lines.append("Generated from step_catalog.json\n")
    for device in sorted(catalog["steps"].keys()):
        lines.append(f"## {device}\n")
        ops = catalog["steps"][device]
        for op in sorted(ops.keys()):
            step = ops[op]
            lines.append(f"### {op}\n")
            params = step.get("parameters", [])
            meta = step.get("parameters_meta", {})
            if params:
                lines.append("**Parameters:**")
                for p in params:
                    lines.append(f"- {fmt_param(p, meta.get(p, {}))}")
            else:
                lines.append("**Parameters:** none")
            containers = step.get("containers", [])
            if containers:
                lines.append("**Containers:**")
                for c in containers:
                    parts = [c.get("container", "")]
                    if c.get("lid_state"):
                        parts.append(f"lid: {c['lid_state']}")
                    if c.get("location"):
                        parts.append(f"location: {c['location']}")
                    lines.append(f"- {'; '.join(parts)}")
            else:
                lines.append("**Containers:** none")
            lines.append("")  # spacer
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Markdown docs from catalog.")
    parser.add_argument("--catalog", default="step_catalog.json")
    parser.add_argument("--output", default="docs/step_reference.md")
    args = parser.parse_args()

    catalog = load_catalog(Path(args.catalog))
    md = generate_md(catalog)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

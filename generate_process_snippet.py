#!/usr/bin/env python3
"""
Create Momentum-style code chunks for selected process steps using the
precomputed step_catalog.json. This is intended to drive a deterministic
fill-in-the-blanks workflow: you supply which steps to include, and the script
prints the exact parameters and container fields that must be filled.

Example:
    python generate_process_snippet.py \\
        --catalog step_catalog.json \\
        --operations "B_XPeel:Remove Seal,A_Combi_Shelf:Dispense"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_catalog(path: Path) -> Dict:
    if not path.exists():
        raise SystemExit(f"Catalog not found: {path}")
    return json.loads(path.read_text())


def format_container(container_entry: Dict) -> str:
    parts: List[str] = [container_entry["container"]]
    if container_entry.get("lid_state"):
        parts.append(f"'{container_entry['lid_state']}'")
    if container_entry.get("location"):
        parts.append(f"in '{container_entry['location']}'")
    return " ".join(parts)


def render_step(device: str, op: str, step: Dict) -> str:
    params = step.get("parameters", [])
    containers = step.get("containers", [])
    param_body = ", ".join(f"{p}=<REQUIRED>" for p in params) or "<no params>"
    container_lines = (
        "    " + " | ".join(format_container(c) for c in containers) + " GetMyOwnContainer;"
        if containers
        else "    <no container specified>;"
    )
    lines = [
        f"{device} [{op}]",
        f"    ({param_body})",
        container_lines,
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Momentum process snippets for selected steps."
    )
    parser.add_argument(
        "--catalog",
        default="step_catalog.json",
        help="Path to the consolidated catalog JSON.",
    )
    parser.add_argument(
        "--operations",
        required=True,
        help="Comma-separated list like \"Device:Operation,Device:Operation\".",
    )
    args = parser.parse_args()

    catalog = load_catalog(Path(args.catalog))
    steps = catalog.get("steps", {})

    requests = [item.strip() for item in args.operations.split(",") if item.strip()]
    if not requests:
        raise SystemExit("No operations provided.")

    for req in requests:
        if ":" not in req:
            print(f"[skip] Expected Device:Operation format, got {req}")
            continue
        device, op = req.split(":", 1)
        if device not in steps:
            print(f"[missing device] {device}")
            continue
        if op not in steps[device]:
            print(f"[missing operation] {device}:{op}")
            continue
        snippet = render_step(device, op, steps[device][op])
        print(snippet)
        print()  # spacer between snippets


if __name__ == "__main__":
    main()

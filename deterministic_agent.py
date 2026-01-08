#!/usr/bin/env python3
"""
Deterministic, catalog-backed CLI for Momentum process building and inspection.

Subcommands:
  list-devices                       -> prints device names
  list-operations --device DEV       -> prints operations for a device
  describe-step --device DEV --op OP -> prints params, defaults/ranges, containers
  build-process                      -> builds a Momentum .txt from ordered steps

All answers are derived from step_catalog.json; no free-form generation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_CATALOG = Path("data/generated/step_catalog.json")


def load_catalog(path: Path) -> Dict:
    if not path.exists():
        raise SystemExit(f"Catalog not found: {path}")
    return json.loads(path.read_text())


def parse_steps_arg(arg: str) -> List[Tuple[str, str, Dict[str, str], str]]:
    """
    Parse step specs like:
      "Device:Operation;param=value;param2=value;container=I_PCR_96_Blue|Device2:Op2"
    """
    steps: List[Tuple[str, str, Dict[str, str], str]] = []
    if not arg:
        return steps
    entries = [s.strip() for s in arg.split("|") if s.strip()]
    for entry in entries:
        if ":" not in entry:
            raise SystemExit(f"Invalid step spec (need Device:Operation): {entry}")
        device, rest = entry.split(":", 1)
        chunks = [c for c in rest.split(";") if c]
        if not chunks:
            raise SystemExit(f"Missing operation name after device in spec: {entry}")
        operation, overrides_chunks = chunks[0], chunks[1:]
        overrides: Dict[str, str] = {}
        cont_override = ""
        for chunk in overrides_chunks:
            if "=" not in chunk:
                raise SystemExit(f"Override must be key=value, got: {chunk}")
            k, v = chunk.split("=", 1)
            key = k.strip()
            if key.lower() in {"container", "container_override"}:
                cont_override = v.strip()
            else:
                overrides[key] = v.strip()
        steps.append((device, operation, overrides, cont_override))
    return steps


def build_process_block(
    catalog: Dict,
    steps_spec: List[Tuple[str, str, Dict[str, str]]],
    process_name: str,
    base_path: Path,
) -> str:
    base_lines = base_path.read_text().splitlines()
    header = slice_header(base_lines)
    block = process_block(catalog, steps_spec, process_name)
    return "\n".join(header + block) + "\n"


def slice_header(base_lines: List[str]) -> List[str]:
    """Return everything before the first 'process [' line."""
    for idx, line in enumerate(base_lines):
        if line.strip().startswith("process "):
            return base_lines[:idx]
    raise SystemExit("Could not find process section in base file.")


def process_block(
    catalog: Dict,
    steps_spec: List[Tuple[str, str, Dict[str, str], str]],
    process_name: str,
) -> List[str]:
    def esc(val: str) -> str:
        return val.replace("'", "''")

    out: List[str] = []
    indent1 = "\t"
    indent2 = "\t\t"
    indent3 = "\t\t\t"

    out.append(f"{indent1}process [{process_name}]")
    out.append(f"{indent1}{{")
    out.append(f"{indent2}// Process steps")

    for device, op, overrides, cont_override in steps_spec:
        if device not in catalog["steps"]:
            raise SystemExit(f"Device not in catalog: {device}")
        if op not in catalog["steps"][device]:
            raise SystemExit(f"Operation not in catalog for {device}: {op}")

        step = catalog["steps"][device][op]
        params = step.get("parameters", [])
        meta = step.get("parameters_meta", {})
        containers = step.get("containers", [])
        if cont_override:
            containers = [{**c, "container": cont_override} for c in containers]

        param_parts = []
        for name in params:
            if name in overrides and overrides[name] != "":
                val = overrides[name]
            elif name in meta and meta[name].get("default") is not None:
                val = str(meta[name]["default"])
            else:
                val = "<FILL>"
            param_parts.append(f"{name} = '{esc(val)}'")

        param_line = ", ".join(param_parts)

        out.append(f"{indent2}{device} [{op}]")
        if containers:
            out.append(f"{indent3}({param_line})")
            for cont in containers:
                cont_bits = [cont["container"]]
                if cont.get("lid_state"):
                    cont_bits.append(f"'{cont['lid_state']}'")
                if cont.get("location"):
                    cont_bits.append(f"in '{cont['location']}'")
                cont_str = " ".join(cont_bits)
                out.append(f"{indent3}{cont_str} GetMyOwnContainer;")
        else:
            out.append(f"{indent3}({param_line});")

        out.append("")  # spacer

    out.append(f"{indent1}}}")
    out.append("}")
    return out


def insert_pools_if_needed(
    header: List[str], catalog: Dict, steps_spec: List[Tuple[str, str, Dict[str, str], str]]
) -> List[str]:
    pools_needed = set()
    pools = catalog.get("pools", {})
    for device, _, _, _ in steps_spec:
        if device in pools:
            pools_needed.add(device)
    if not pools_needed:
        return header
    has_pools = any(line.strip().startswith("pools") for line in header)
    if has_pools:
        return header
    block = []
    block.append("\t// Device pools")
    block.append("\tpools")
    block.append("\t{")
    for name in sorted(pools_needed):
        info = pools[name]
        members = ",".join(info.get("members", []))
        block.append(f"\t\t{info.get('type','StoragePool')} {name} () {members} ;")
    block.append("\t}")
    new_header: List[str] = []
    inserted = False
    for line in header:
        if not inserted and line.strip().startswith("variables"):
            new_header.extend(block)
            inserted = True
        new_header.append(line)
    if not inserted:
        new_header.extend(block)
    return new_header


def cmd_list_devices(args):
    catalog = load_catalog(Path(args.catalog))
    for dev in sorted(catalog["steps"].keys()):
        print(dev)


def cmd_list_operations(args):
    catalog = load_catalog(Path(args.catalog))
    if args.device not in catalog["steps"]:
        raise SystemExit(f"Device not in catalog: {args.device}")
    for op in sorted(catalog["steps"][args.device].keys()):
        print(op)


def cmd_describe_step(args):
    catalog = load_catalog(Path(args.catalog))
    if args.device not in catalog["steps"]:
        raise SystemExit(f"Device not in catalog: {args.device}")
    steps = catalog["steps"][args.device]
    if args.op not in steps:
        raise SystemExit(f"Operation not in catalog for {args.device}: {args.op}")
    info = steps[args.op]
    print(json.dumps(info, indent=2))


def cmd_build_process(args):
    catalog = load_catalog(Path(args.catalog))
    steps_spec = parse_steps_arg(args.steps)
    if not steps_spec:
        raise SystemExit("No steps provided.")
    header = slice_header(Path(args.base).read_text().splitlines())
    header = insert_pools_if_needed(header, catalog, steps_spec)
    output_text = "\n".join(header + process_block(catalog, steps_spec, args.process_name)) + "\n"
    Path(args.output).write_text(output_text)
    print(f"Wrote {args.output}")


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic Momentum helper (catalog-backed)."
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG),
        help="Path to step_catalog.json",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list-devices", help="List all devices")
    p1.set_defaults(func=cmd_list_devices)

    p2 = sub.add_parser("list-operations", help="List operations for a device")
    p2.add_argument("--device", required=True)
    p2.set_defaults(func=cmd_list_operations)

    p3 = sub.add_parser("describe-step", help="Describe parameters/containers for a step")
    p3.add_argument("--device", required=True)
    p3.add_argument("--op", required=True)
    p3.set_defaults(func=cmd_describe_step)

    p4 = sub.add_parser("build-process", help="Build a Momentum process file")
    p4.add_argument("--base", default="data/raw/Momentum_db2.txt", help="Base DB file (header source)")
    p4.add_argument("--process-name", default="Generated_Process")
    p4.add_argument(
        "--steps",
        required=True,
        help="Step list like \"Device:Operation;param=value|Device2:Operation\"",
    )
    p4.add_argument("--output", default="generated_process.txt")
    p4.set_defaults(func=cmd_build_process)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Extract a deterministic catalog of Momentum process steps, devices, pools,
variables, and inventory containers from the supplied Momentum_db text files.

Default usage (from this folder):
    python generate_step_catalog.py \
        --inputs Momentum_db1.txt Momentum_db2.txt \
        --inventory inventory_containers.yaml \
        --output step_catalog.json
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass
class StepEntry:
    parameters: List[str] = field(default_factory=list)
    containers: Set[Tuple[str, Optional[str], Optional[str]]] = field(
        default_factory=set
    )
    param_values: Dict[str, Set[str]] = field(default_factory=dict)


def parse_inventory_containers(path: Path) -> List[str]:
    """Simple parse of inventory_containers.yaml to capture the container list."""
    containers: List[str] = []
    if not path.exists():
        return containers

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            containers.append(stripped[2:].strip())
    return containers


def parse_container(line: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """Parse container usage lines like:
    I_PCR_96_Green 'Unlidded' in 'Device:Nest' GetMyOwnContainer;
    """
    text = line.strip().rstrip(";")
    text = text.replace("GetMyOwnContainer", "").strip()
    if not text:
        return None
    match = re.match(
        r"(?P<container>[A-Za-z0-9_]+)"
        r"(?:\s+'(?P<lid>[^']+)')?"
        r"(?:\s+in\s+'(?P<loc>[^']+)')?",
        text,
    )
    if not match:
        return None
    return (match.group("container"), match.group("lid"), match.group("loc"))


def parse_param_assignments(inner: str) -> List[Tuple[str, str]]:
    """Return (name, value) pairs from the parameter body."""
    assigns: List[Tuple[str, str]] = []
    # Quoted values
    for m in re.finditer(r"([A-Za-z0-9_]+)\s*=\s*'([^']*)'", inner):
        assigns.append((m.group(1), m.group(2)))
    # Unquoted values (keep even if quoted were found)
    for m in re.finditer(r"([A-Za-z0-9_]+)\s*=\s*([^,' )]+)", inner):
        if (m.group(1), m.group(2)) not in assigns:
            assigns.append((m.group(1), m.group(2)))
    return assigns


def add_step(
    steps: Dict[str, Dict[str, StepEntry]],
    device: str,
    operation: str,
    param_names: Iterable[str],
    param_assignments: Iterable[Tuple[str, str]],
    container_info: Optional[Tuple[str, Optional[str], Optional[str]]],
) -> None:
    dev_dict = steps.setdefault(device, {})
    entry = dev_dict.setdefault(operation, StepEntry())
    for name in param_names:
        if name not in entry.parameters:
            entry.parameters.append(name)
    for name, value in param_assignments:
        entry.param_values.setdefault(name, set()).add(value)
    if container_info:
        entry.containers.add(container_info)


def parse_momentum_files(paths: Iterable[Path]):
    devices: Set[str] = set()
    variables: Set[str] = set()
    pools: Dict[str, Dict[str, Set[str]]] = {}
    steps: Dict[str, Dict[str, StepEntry]] = {}

    for path in paths:
        lines = path.read_text().splitlines()

        in_devices = in_vars = in_pools = False
        current_pool: Optional[Dict[str, object]] = None
        state: Optional[str] = None  # params | container
        current_step: Optional[Tuple[str, str]] = None
        param_lines: List[str] = []
        paren_depth = 0

        for raw in lines:
            stripped = raw.strip()
            if not stripped or stripped.startswith("//"):
                continue

            # Devices block
            if stripped.startswith("devices"):
                in_devices, in_vars, in_pools = True, False, False
                continue
            if in_devices:
                if stripped.startswith("}"):
                    in_devices = False
                    continue
                m_dev = re.match(r"([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)", stripped)
                if m_dev:
                    devices.add(m_dev.group(2))
                continue

            # Pools block
            if stripped.startswith("pools"):
                in_pools, in_devices, in_vars = True, False, False
                current_pool = None
                continue
            if in_pools:
                if stripped.startswith("}"):
                    in_pools = False
                    current_pool = None
                    continue
                if current_pool is None:
                    m_pool = re.match(
                        r"(StoragePool|OperationPool)\s+([A-Za-z0-9_]+)", stripped
                    )
                    if m_pool:
                        current_pool = {
                            "type": m_pool.group(1),
                            "name": m_pool.group(2),
                            "lines": [],
                        }
                    continue
                current_pool["lines"].append(stripped)  # type: ignore[index]
                if ";" in stripped:
                    member_text = " ".join(current_pool["lines"])  # type: ignore[index]
                    if ")" in member_text:
                        member_text = member_text.split(")", 1)[1]
                    members = [
                        m.strip()
                        for m in member_text.replace(";", "").split(",")
                        if m.strip()
                    ]
                    pool_name = current_pool["name"]  # type: ignore[index]
                    pools.setdefault(
                        pool_name, {"type": current_pool["type"], "members": set()}  # type: ignore[index]
                    )
                    pools[pool_name]["members"].update(members)  # type: ignore[index]
                    current_pool = None
                continue

            # Variables block
            if stripped.startswith("variables"):
                in_vars, in_devices, in_pools = True, False, False
                continue
            if in_vars:
                if stripped.startswith("}"):
                    in_vars = False
                    continue
                m_var = re.match(r"(String|Integer|Boolean)\s+([A-Za-z0-9_]+)", stripped)
                if m_var:
                    variables.add(m_var.group(2))
                continue

            # Process steps
            m_step = re.match(r"([A-Za-z0-9_]+)\s+\[([^\]]+)\]", stripped)
            if m_step:
                current_step = (m_step.group(1), m_step.group(2))
                state = "params"
                param_lines = []
                paren_depth = 0
                continue

            if state == "params":
                param_lines.append(stripped)
                paren_depth += stripped.count("(") - stripped.count(")")
                if paren_depth <= 0:
                    param_text = " ".join(param_lines)
                    inner = (
                        param_text.split("(", 1)[1].rsplit(")", 1)[0]
                        if "(" in param_text and ")" in param_text
                        else ""
                    )
                    assignments = parse_param_assignments(inner)
                    param_names = [name for name, _ in assignments] or re.findall(
                        r"([A-Za-z0-9_]+)\s*=", inner
                    )
                    if stripped.rstrip().endswith(";"):
                        add_step(
                            steps,
                            current_step[0],  # type: ignore[index]
                            current_step[1],  # type: ignore[index]
                            param_names,
                            assignments,
                            None,
                        )
                        state = current_step = None
                        param_lines = []
                    else:
                        state = "container"
                continue

            if state == "container":
                container_info = parse_container(stripped)
                param_text = " ".join(param_lines)
                inner = (
                    param_text.split("(", 1)[1].rsplit(")", 1)[0]
                    if "(" in param_text and ")" in param_text
                    else ""
                )
                assignments = parse_param_assignments(inner)
                param_names = [name for name, _ in assignments] or re.findall(
                    r"([A-Za-z0-9_]+)\s*=", inner
                )
                add_step(
                    steps,
                    current_step[0],  # type: ignore[index]
                    current_step[1],  # type: ignore[index]
                    param_names,
                    assignments,
                    container_info,
                )
                if stripped.endswith(";"):
                    state = current_step = None
                    param_lines = []
                continue

    return devices, variables, pools, steps


def serialize_steps(steps: Dict[str, Dict[str, StepEntry]]):
    def infer_meta(values: Set[str]) -> Dict[str, object]:
        if not values:
            return {"type": "unknown", "default": None, "observed_values": []}
        vals = sorted(values)

        def is_bool(v: str) -> bool:
            return v.lower() in {"yes", "no", "true", "false"}

        def parse_duration(v: str) -> Optional[int]:
            parts = v.split(":")
            if len(parts) != 3:
                return None
            try:
                h, m, s = map(float, parts)
                return int(h * 3600 + m * 60 + s)
            except ValueError:
                return None

        def parse_number(v: str) -> Optional[float]:
            try:
                return float(v)
            except ValueError:
                return None

        if all(is_bool(v) for v in vals):
            return {
                "type": "boolean",
                "default": vals[0],
                "observed_values": vals,
            }

        durations = [parse_duration(v) for v in vals]
        if all(d is not None for d in durations):
            min_idx = durations.index(min(durations))  # type: ignore[arg-type]
            max_idx = durations.index(max(durations))  # type: ignore[arg-type]
            return {
                "type": "time",
                "default": vals[0],
                "observed_values": vals,
                "min": vals[min_idx],
                "max": vals[max_idx],
            }

        numbers = [parse_number(v) for v in vals]
        if all(n is not None for n in numbers):
            min_val = min(numbers)  # type: ignore[arg-type]
            max_val = max(numbers)  # type: ignore[arg-type]
            min_idx = numbers.index(min_val)
            max_idx = numbers.index(max_val)
            return {
                "type": "number",
                "default": vals[0],
                "observed_values": vals,
                "min": vals[min_idx],
                "max": vals[max_idx],
            }

        return {
            "type": "string",
            "default": vals[0],
            "observed_values": vals,
        }

    return {
        device: {
            op: {
                "parameters": entry.parameters,
                "containers": [
                    {"container": c, "lid_state": lid, "location": loc}
                    for c, lid, loc in sorted(entry.containers)
                ],
                "parameters_meta": {
                    name: infer_meta(values)
                    for name, values in sorted(entry.param_values.items())
                },
            }
            for op, entry in sorted(ops.items())
        }
        for device, ops in sorted(steps.items())
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic step catalog from Momentum DB files."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=["Momentum_db1.txt", "Momentum_db2.txt"],
        help="Momentum DB text files to parse.",
    )
    parser.add_argument(
        "--inventory",
        default="inventory_containers.yaml",
        help="Path to inventory_containers.yaml.",
    )
    parser.add_argument(
        "--output",
        default="step_catalog.json",
        help="Where to write the consolidated catalog.",
    )
    parser.add_argument(
        "--split-dir",
        default=None,
        help="Optional directory to also write split artifacts (devices, pools, variables, steps, containers).",
    )
    args = parser.parse_args()

    input_paths = [Path(p) for p in args.inputs]
    for p in input_paths:
        if not p.exists():
            raise SystemExit(f"Input file not found: {p}")

    inventory = parse_inventory_containers(Path(args.inventory))
    devices, variables, pools, steps = parse_momentum_files(input_paths)

    data = {
        "inventory_containers": inventory,
        "devices": sorted(devices),
        "pools": {
            name: {"type": info["type"], "members": sorted(info["members"])}
            for name, info in sorted(pools.items())
        },
        "variables": sorted(variables),
        "steps": serialize_steps(steps),
    }

    Path(args.output).write_text(json.dumps(data, indent=2))
    print(f"Wrote catalog to {args.output}")

    if args.split_dir:
        split_dir = Path(args.split_dir)
        split_dir.mkdir(parents=True, exist_ok=True)

        # Core lists/mappings
        (split_dir / "inventory_containers.json").write_text(
            json.dumps(data["inventory_containers"], indent=2)
        )
        (split_dir / "devices.json").write_text(
            json.dumps(data["devices"], indent=2)
        )
        (split_dir / "pools.json").write_text(
            json.dumps(data["pools"], indent=2)
        )
        (split_dir / "variables.json").write_text(
            json.dumps(data["variables"], indent=2)
        )
        (split_dir / "steps.json").write_text(
            json.dumps(data["steps"], indent=2)
        )

        # Per-device step files
        per_device_dir = split_dir / "steps_by_device"
        per_device_dir.mkdir(exist_ok=True)
        for device, ops in data["steps"].items():
            (per_device_dir / f"{device}.json").write_text(
                json.dumps({device: ops}, indent=2)
            )
        print(f"Wrote split artifacts to {split_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Streamlit UI for assembling Momentum process files.

Features:
- Keeps devices/variables/pools from a chosen base DB file (static header).
- Lets you pick steps (Device + Operation) from the catalog and order them.
- For each step, exposes parameter fields (prefilled with catalog defaults) for overrides.
- Generates a Momentum-format text file ready for download.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st


CATALOG_PATH = Path("data/generated/step_catalog.json")
BASE_OPTIONS_ALL = sorted([str(p) for p in Path("data/raw").glob("Momentum_db*.txt")])
DEFAULT_BASE = "data/raw/Momentum_db2.txt" if Path("data/raw/Momentum_db2.txt").exists() else (BASE_OPTIONS_ALL[0] if BASE_OPTIONS_ALL else "")


def load_catalog(path: Path) -> Dict:
    if not path.exists():
        st.error(f"Catalog not found: {path}")
        st.stop()
    return json.loads(path.read_text())


def slice_header(base_lines: List[str]) -> List[str]:
    """Return everything before the first 'process [' line."""
    for idx, line in enumerate(base_lines):
        if line.strip().startswith("process "):
            return base_lines[:idx]
    st.error("Could not find process section in base file.")
    st.stop()


def insert_pools_if_needed(
    header: List[str], catalog: Dict, steps_spec: List[Tuple[str, str, Dict[str, str], str]]
) -> List[str]:
    pools_needed = set()
    pools = catalog.get("pools", {})
    for item in steps_spec:
        device = item[0]
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


def build_process_block(
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

    for item in steps_spec:
        # backward compat if tuple lacks override
        if len(item) == 3:
            device, op, overrides = item  # type: ignore[misc]
            cont_override = ""
        else:
            device, op, overrides, cont_override = item  # type: ignore[misc]
        step = catalog["steps"][device][op]
        params = step.get("parameters", [])
        meta = step.get("parameters_meta", {})
        containers = step.get("containers", [])
        if cont_override:
            containers = [
                {**c, "container": cont_override}
                for c in containers
            ]

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


def main() -> None:
    st.title("Momentum Process Builder")
    st.caption("Pick steps, override parameters, and generate a Momentum-compatible process file.")

    catalog = load_catalog(CATALOG_PATH)
    inventory_choices = catalog.get("inventory_containers", [])

    base_file_choice = st.selectbox(
        "Base DB file (static header to copy)",
        BASE_OPTIONS_ALL,
        index=BASE_OPTIONS_ALL.index(DEFAULT_BASE) if DEFAULT_BASE in BASE_OPTIONS_ALL else 0 if BASE_OPTIONS_ALL else None,
    )
    base_file_manual = st.text_input("Or specify a custom base file path", value=base_file_choice or DEFAULT_BASE)
    base_file = base_file_manual.strip()
    process_name = st.text_input("Process name", value="Generated_Process")

    # Session state init
    if "steps" not in st.session_state:
        st.session_state.steps = []  # list of (device, op, overrides, container_override)

    device = st.selectbox("Device", sorted(catalog["steps"].keys()))
    operation = st.selectbox("Operation", sorted(catalog["steps"][device].keys()))
    if st.button("Add step"):
        st.session_state.steps.append((device, operation, {}, ""))  # last field is container override

    st.write("### Current steps (in order)")
    new_steps = []
    for idx, item in enumerate(st.session_state.steps):
        # Backward compatibility: older tuples without container override
        if len(item) == 3:
            dev, op, overrides = item
            cont_override = ""
        else:
            dev, op, overrides, cont_override = item
        cols = st.columns([6, 1, 1])
        with cols[0]:
            st.write(f"{idx+1}. {dev} [{op}]")
        with cols[1]:
            if st.button("⬆️", key=f"up_{idx}") and idx > 0:
                st.session_state.steps[idx - 1], st.session_state.steps[idx] = (
                    st.session_state.steps[idx],
                    st.session_state.steps[idx - 1],
                )
        with cols[2]:
            if st.button("🗑️", key=f"del_{idx}"):
                continue  # skip adding to new list

        # Overrides UI
        st.write("Overrides:")
        step_data = catalog["steps"][dev][op]
        params = step_data.get("parameters", [])
        meta = step_data.get("parameters_meta", {})
        updated_overrides = dict(overrides)
        for p in params:
            default_val = updated_overrides.get(p, meta.get(p, {}).get("default", ""))
            updated_overrides[p] = st.text_input(
                f"{p} ({meta.get(p, {}).get('type', 'unknown')})",
                value=str(default_val) if default_val is not None else "",
                key=f"{idx}_{p}",
            )
        # Container override from inventory
        cont_override = st.selectbox(
            "Container override (inventory)",
            options=[""] + inventory_choices,
            index=([""] + inventory_choices).index(cont_override) if cont_override in inventory_choices else 0,
            key=f"cont_{idx}",
        )

        new_steps.append((dev, op, updated_overrides, cont_override))
        st.markdown("---")

    st.session_state.steps = new_steps

    if st.button("Generate process file"):
        if not st.session_state.steps:
            st.warning("Add at least one step.")
            st.stop()

        base_lines = Path(base_file).read_text().splitlines()
        header = slice_header(base_lines)
        header = insert_pools_if_needed(header, catalog, st.session_state.steps)
        process_block = build_process_block(catalog, st.session_state.steps, process_name)
        output_text = "\n".join(header + process_block) + "\n"

        st.success("Process generated.")
        st.download_button(
            "Download process file",
            data=output_text,
            file_name="generated_process.txt",
            mime="text/plain",
        )
        st.text_area("Preview", value=output_text, height=300)


if __name__ == "__main__":
    main()

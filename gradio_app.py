#!/usr/bin/env python3
"""
Gradio UI to assemble a Momentum process file.

Use the "steps" field with the same format as the CLI:
  Device:Operation;param=value;param2=value|Device2:Operation

On launch with share=True, Gradio prints a public link you can click.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import gradio as gr


CATALOG_PATH = Path("step_catalog.json")
BASE_OPTIONS = ["Momentum_db2.txt", "Momentum_db1.txt"]


def load_catalog(path: Path) -> Dict:
    if not path.exists():
        raise RuntimeError(f"Catalog not found: {path}")
    return json.loads(path.read_text())


CATALOG = load_catalog(CATALOG_PATH)


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
            raise ValueError(f"Invalid step spec (need Device:Operation): {entry}")
        device, rest = entry.split(":", 1)
        chunks = [c for c in rest.split(";") if c]
        if not chunks:
            raise ValueError(f"Missing operation name after device in spec: {entry}")
        operation, overrides_chunks = chunks[0], chunks[1:]
        overrides: Dict[str, str] = {}
        cont_override = ""
        for chunk in overrides_chunks:
            if "=" not in chunk:
                raise ValueError(f"Override must be key=value, got: {chunk}")
            k, v = chunk.split("=", 1)
            key = k.strip()
            if key.lower() in {"container", "container_override"}:
                cont_override = v.strip()
            else:
                overrides[key] = v.strip()
        steps.append((device, operation, overrides, cont_override))
    return steps


def slice_header(base_lines: List[str]) -> List[str]:
    """Return everything before the first 'process [' line."""
    for idx, line in enumerate(base_lines):
        if line.strip().startswith("process "):
            return base_lines[:idx]
    raise RuntimeError("Could not find process section in base file.")


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

    for device, op, overrides, cont_override in steps_spec:
        if device not in catalog["steps"]:
            raise RuntimeError(f"Device not in catalog: {device}")
        if op not in catalog["steps"][device]:
            raise RuntimeError(f"Operation not in catalog for {device}: {op}")

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


def generate(base_file: str, process_name: str, steps_text: str):
    try:
        steps_spec = parse_steps_arg(steps_text)
    except Exception as e:
        return f"Error parsing steps: {e}"

    if not steps_spec:
        return "No steps provided."

    base_path = Path(base_file)
    if not base_path.exists():
        return f"Base file not found: {base_file}"

    try:
        base_lines = base_path.read_text().splitlines()
        header = slice_header(base_lines)
        header = insert_pools_if_needed(header, CATALOG, steps_spec)
        process_block = build_process_block(CATALOG, steps_spec, process_name)
        output_text = "\n".join(header + process_block) + "\n"
    except Exception as e:
        return f"Error generating process: {e}"

    return output_text


DESCRIPTION = """Enter steps as:
Device:Operation;param=value;param2=value|Device2:Operation;param=value
Unspecified params use catalog defaults or <FILL>.
"""


def main():
    with gr.Blocks() as demo:
        gr.Markdown("# Momentum Process Builder (Gradio)")
        gr.Markdown(DESCRIPTION)
        base = gr.Dropdown(choices=BASE_OPTIONS, value=BASE_OPTIONS[0], label="Base DB (header source)")
        pname = gr.Textbox(value="Generated_Process", label="Process name")
        steps = gr.Textbox(
            lines=4,
            label="Steps spec",
            placeholder="B_XPeel:Remove Seal;AdhereTime=3.5|B_Centrifuge:Spin;SpinGs=1200",
        )
        btn = gr.Button("Generate")
        output = gr.Textbox(label="Generated process text", lines=12)

        btn.click(fn=generate, inputs=[base, pname, steps], outputs=[output])

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_api=False,
        allowed_paths=[str(Path("."))],
    )


if __name__ == "__main__":
    main()

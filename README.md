# Momentum Process Script Generator

Deterministic tools to turn Momentum DB exports into reproducible process scripts. Everything is data-driven—no free-form generation—so outputs are predictable and auditable.

## Goal
- Ingest Momentum DB exports + inventory.
- Build a finite catalog of devices, pools, variables, and steps (with params, defaults/ranges, containers).
- Generate Momentum-compatible process files by selecting ordered steps and overrides.
- Browse via optional UI; primary flow is CLI for reproducibility.

## Layout
- data/raw/ — source DB exports (`Momentum_db1.txt`, `Momentum_db2.txt`) + `inventory_containers.yaml`
- data/generated/ — outputs (catalog JSON + split parts)
- examples/ — sample generated process files
- docs/ — audit report (`audit_report.tex`), step reference (`step_reference.md`)
- Scripts: `generate_step_catalog.py`, `generate_process_file.py`, `generate_process_snippet.py`, `generate_docs.py`, `deterministic_agent.py`, `streamlit_app.py`, `gradio_app.py`

## Quick start (rebuild catalog + docs)
```bash
cd viku/PlayGround/Momentum_Process_ScriptGen
python generate_step_catalog.py   --inputs data/raw/Momentum_db1.txt data/raw/Momentum_db2.txt   --inventory data/raw/inventory_containers.yaml   --output data/generated/step_catalog.json   --split-dir data/generated/catalog_parts

python generate_docs.py --catalog data/generated/step_catalog.json --output docs/step_reference.md
```

## Build a process (deterministic CLI)
```bash
# list devices / ops
python deterministic_agent.py list-devices
python deterministic_agent.py list-operations --device B_XPeel

# describe one step (params + defaults/ranges + containers)
python deterministic_agent.py describe-step --device B_XPeel --op "Remove Seal"

# build a process file (header from base DB, steps from combined catalog)
python deterministic_agent.py build-process   --base data/raw/Momentum_db2.txt   --process-name My_Process   --steps "B_XPeel:Remove Seal;AdhereTime=2.5;container=I_PCR_96_Blue|A_Combi_Shelf:Dispense;DispenseVolume=50;PlateType=96 standard (15mm);PrimeEnabled=No"   --output examples/my_process.txt
```
- `container=` override is optional; defaults come from the DB/catalog.
- Pools are injected if needed and missing from the base header.
- All containers for a step are emitted; single quotes in values are escaped.

## Snippets (checklist)
```bash
python generate_process_snippet.py   --catalog data/generated/step_catalog.json   --operations "B_XPeel:Remove Seal,A_Combi_Shelf:Dispense"
```
Shows required params and container expectations with `<REQUIRED>` markers.

## UI (optional)
```bash
cd viku/PlayGround/Momentum_Process_ScriptGen
streamlit run streamlit_app.py
# or
python gradio_app.py
```
Pick base DB, select steps, edit params, optionally override containers from inventory, download the `.txt`.

## Docs
- Static reference: `docs/step_reference.md` (regenerate with `generate_docs.py`).
- Audit overview: `docs/audit_report.tex` (compile externally to PDF if needed).

## Notes
- Paths are relative; no secrets or hardcoded machine paths.
- Catalog is built from both DB exports; base file supplies only the static header (devices/variables/pools).
- Use `data/raw/Momentum_db2.txt` as base to include pools; if a base lacks pools, needed pools are injected automatically.

## Suggested next steps
- Add a `validate` command to fail on any `<FILL>` or invalid container overrides.
- Optional CI: py_compile + catalog build check.

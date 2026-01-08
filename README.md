# Momentum DB Step Catalog

This folder contains the Momentum DB exports (`data/raw/Momentum_db1.txt`, `data/raw/Momentum_db2.txt`) plus utilities to derive a deterministic catalog of everything you need to build workflows (devices, pools, variables, and per-step requirements).

## Files
- `generate_step_catalog.py` — parser that reads one or more Momentum DB text files and emits a consolidated catalog.
- `generate_process_snippet.py` — creates fill-in-the-blank code chunks for specific device operations using the catalog.
- `generate_process_file.py` — builds a full Momentum-ready text file by keeping the static header (devices/variables/pools) from a base file and swapping in a generated process block.
- `streamlit_app.py` — interactive UI to pick steps, override parameters, and download a Momentum-ready process file.
- `deterministic_agent.py` — CLI “agent” to list devices/ops, describe steps, and build process files (catalog-backed).
- `generate_docs.py` — produces static Markdown docs of all steps/params/containers from the catalog.
- `data/raw/` — source DB exports and `inventory_containers.yaml`.
- `data/generated/step_catalog.json` — generated output: finite lists of devices, pools, variables, and every unique step with its required parameters and container expectations.
- `data/generated/catalog_parts/` — split outputs for direct consumption (per-topic and per-device JSON).

## What the catalog contains
- `inventory_containers`: canonical container names from `inventory_containers.yaml`.
- `devices`: every device declared across the DB files.
- `pools`: storage/operation pools with their members (e.g., hotel pools, shaker pools).
- `variables`: profile-level variables.
- `steps`: a mapping of `device -> operation -> {parameters, containers, parameters_meta}` where:
  - `parameters` is the list of parameter names that must be provided for that operation.
  - `containers` lists the required container type, lid state (if any), and target location (nest).
  - `parameters_meta` includes inferred type/default/range based on observed values in the DB files (best-effort: boolean/number/time/string).

Use this to drive a deterministic form-like UI: user selects a step, and the catalog tells you exactly which fields to expose and which container type/location is expected.

## How to run
From this directory:
```bash
python generate_step_catalog.py \
  --inputs data/raw/Momentum_db1.txt data/raw/Momentum_db2.txt \
  --inventory data/raw/inventory_containers.yaml \
  --output data/generated/step_catalog.json \
  --split-dir data/generated/catalog_parts
```

Arguments (all optional; defaults shown):
- `--inputs`: one or more Momentum DB `.txt` files to parse.
- `--inventory`: container list file (`inventory_containers.yaml`).
- `--output`: path for the consolidated JSON (`step_catalog.json`).
- `--split-dir`: if set, writes topic-specific files into this folder plus per-device step files under `steps_by_device/`.

## Generate process snippets (fill-in-the-blanks)
Use the catalog to print the exact parameters and container requirements for selected steps:
```bash
# Example: two operations
python generate_process_snippet.py \
  --catalog data/generated/step_catalog.json \
  --operations "B_XPeel:Remove Seal,A_Combi_Shelf:Dispense"
```

Sample output:
```
B_XPeel [Remove Seal]
    (AdhereTime=<REQUIRED>, Duration=<REQUIRED>, Enabled=<REQUIRED>, MaxDelaySpecified=<REQUIRED>, MinDelay=<REQUIRED>, ParameterSet=<REQUIRED>, PeelTimeOut=<REQUIRED>, RequestedMaxDelay=<REQUIRED>, ReserveForIteration=<REQUIRED>, RunOnAbortedIteration=<REQUIRED>, SkipOnError=<REQUIRED>, SpoilIfMaxDelayExceeded=<REQUIRED>)
    I_PCR_96_Green 'Unlidded' in 'B_XPeel:Nest' GetMyOwnContainer;

A_Combi_Shelf [Dispense]
    (CassetteID=<REQUIRED>, Column_1=<REQUIRED>, Column_10=<REQUIRED>, Column_11=<REQUIRED>, Column_12=<REQUIRED>, Column_13=<REQUIRED>, Column_14=<REQUIRED>, Column_15=<REQUIRED>, Column_16=<REQUIRED>, Column_17=<REQUIRED>, Column_18=<REQUIRED>, Column_19=<REQUIRED>, Column_2=<REQUIRED>, Column_20=<REQUIRED>, Column_21=<REQUIRED>, Column_22=<REQUIRED>, Column_23=<REQUIRED>, Column_24=<REQUIRED>, Column_25=<REQUIRED>, Column_26=<REQUIRED>, Column_27=<REQUIRED>, Column_28=<REQUIRED>, Column_29=<REQUIRED>, Column_3=<REQUIRED>, Column_30=<REQUIRED>, Column_31=<REQUIRED>, Column_32=<REQUIRED>, Column_33=<REQUIRED>, Column_34=<REQUIRED>, Column_35=<REQUIRED>, Column_36=<REQUIRED>, Column_37=<REQUIRED>, Column_38=<REQUIRED>, Column_39=<REQUIRED>, Column_4=<REQUIRED>, Column_40=<REQUIRED>, Column_41=<REQUIRED>, Column_42=<REQUIRED>, Column_43=<REQUIRED>, Column_44=<REQUIRED>, Column_45=<REQUIRED>, Column_46=<REQUIRED>, Column_47=<REQUIRED>, Column_48=<REQUIRED>, Column_5=<REQUIRED>, Column_6=<REQUIRED>, Column_7=<REQUIRED>, Column_8=<REQUIRED>, Column_9=<REQUIRED>, DefaultToColumn1=<REQUIRED>, DispenseHeight=<REQUIRED>, DispenseOrder=<REQUIRED>, DispenseVolume=<REQUIRED>, DispenseXOffset=<REQUIRED>, DispenseYOffset=<REQUIRED>, FirstCol=<REQUIRED>, FirstRow=<REQUIRED>, Fluid=<REQUIRED>, LastCol=<REQUIRED>, LastRow=<REQUIRED>, MinDelay=<REQUIRED>, PrimeEnabled=<REQUIRED>, PrimeVolume=<REQUIRED>, PumpSpeed=<REQUIRED>, RequestedMaxDelay=<REQUIRED>, ReserveForIteration=<REQUIRED>, RunOnAbortedIteration=<REQUIRED>, SkipOnError=<REQUIRED>, SpoilIfMaxDelayExceeded=<REQUIRED>, Duration=<REQUIRED>, Enabled=<REQUIRED>, MaxDelaySpecified=<REQUIRED>)
    I_PCR_96_Green in 'A_Combi_Shelf:Nest' GetMyOwnContainer;
```
This acts as a checklist: every `<REQUIRED>` must be supplied; container type/lid/location are enforced by the snippet.

## Generate a full process file (templated)
Keeps devices/variables/pools from a base file and replaces only the process steps.
```bash
python generate_process_file.py \
  --base data/raw/Momentum_db2.txt \
  --catalog data/generated/step_catalog.json \
  --process-name My_New_Process \
  --steps "B_XPeel:Remove Seal;AdhereTime=3.0|A_Combi_Shelf:Dispense;DispenseVolume=50" \
  --output generated_process.txt
```
Notes:
- Steps are separated with `|`.
- For each step, use `Device:Operation;param=value;param2=value` to override values. Any parameter not overridden uses the observed default from the catalog, else `<FILL>`.
- The header (devices, variables, pools) is copied verbatim from `--base`, so Momentum can accept the file with no extra edits.

## Example usage in code
```python
import json
from pathlib import Path

catalog = json.loads(Path("data/generated/step_catalog.json").read_text())

# List all operations available on B_XPeel
ops = catalog["steps"]["B_XPeel"].keys()

# Fetch requirements for a specific step
remove_seal = catalog["steps"]["B_XPeel"]["Remove Seal"]
required_params = remove_seal["parameters"]
container_requirements = remove_seal["containers"]
param_meta = remove_seal["parameters_meta"]  # type/default/range per param
```

If you prefer split files, load from `catalog_parts/`:
```python
from pathlib import Path
import json

steps_by_device = json.loads(Path("data/generated/catalog_parts/steps.json").read_text())
b_xpeel_ops = steps_by_device["B_XPeel"]
```

## Interactive UI (Streamlit)
Launch a small UI to assemble a process file:
```bash
cd viku/PlayGround/Momentum_Process_ScriptGen
streamlit run streamlit_app.py
```
What it does:
- Copies the static header (devices/variables/pools) from a selected base DB file.
- Lets you pick Device/Operation pairs from the catalog, order them, and override parameters (prefilled with observed defaults).
- Lets you optionally override containers per step using the inventory list.
- Generates a Momentum-format text file you can download; preview shown in the app.

## Deterministic CLI agent
Catalog-backed commands (no free-form generation):
```bash
# list devices / ops
python deterministic_agent.py list-devices
python deterministic_agent.py list-operations --device B_XPeel

# describe one step (params + defaults/ranges + containers)
python deterministic_agent.py describe-step --device B_XPeel --op "Remove Seal"

# build a process file
python deterministic_agent.py build-process \
  --base data/raw/Momentum_db2.txt \
  --process-name My_Process \
  --steps "B_XPeel:Remove Seal;AdhereTime=2.5|A_Combi_Shelf:Dispense;DispenseVolume=50;PlateType=96 standard (15mm);PrimeEnabled=No" \
  --output my_process.txt
# container override (optional) reserved key: e.g., container=I_PCR_96_Blue
# --steps "B_XPeel:Remove Seal;AdhereTime=2.5;container=I_PCR_96_Blue"
```

## Static docs
Generate Markdown docs for all steps/params/containers:
```bash
python generate_docs.py --catalog data/generated/step_catalog.json --output docs/step_reference.md
```
## Future extension ideas
- Add simple type/default hints per parameter based on device docs.
- Validate that container types referenced in steps exist in `inventory_containers`.
- Emit a JSON Schema to auto-generate forms in a UI.

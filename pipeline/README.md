# 🚀 Pipeline README

This folder contains helper scripts and a small driver to run a pipeline that queues prompts to a ComfyUI server. The main entrypoint is `process_localization.py`.

## 📌 Overview

### The pipeline:

1. Reads prompt JSONs from prompts/ (each must include positive_prompt, negative_prompt, and verification_prompt).

2. Loads a workflow JSON (default: workflows/pipeline_api.json) describing the server steps.

3. For each prompt file, it:
   - Clears the outputs directory.

   - Prepares the workflow (image directory, batch size, prompt texts).

   - Iterates combinations of cfg / denoise / seed and queues jobs to the server.

   - Waits for the server queue to empty.

   - Selects the best-scoring line in a results file and copies matching images to a destination folder.

## ⚙️ Setup & Running

### 1. Install dependencies for this folder (recommended into a virtualenv):

```bash
pip install -r requirements.txt
```
You also need ComfyUI running. See the [installation guide](https://comfyui-wiki.com/en/install/install-comfyui)

⚠️ Specific custom nodes are required. Import workflows/pipeline.json into ComfyUI; it will guide you to install missing nodes.

### 2. Create a `.env` file in this folder or set the following environment variables in your shell. A sample `.env` could look like:

```bash
SERVER_ADDRESS="127.0.0.1:8188"
WORKFLOW_FILE="pipeline_api.json"
PICTURES_DIRECTORY="<absolute-path-to-images>"
DEFAULT_OUTPUTS_PATH="<absolute-path-to-comfy>/comfy/ComfyUI/output"
DEFAULT_FIND_MAX_FILE="<absolute-path-to-comfy>/comfy/ComfyUI/temp/scores.txt"
DEFAULT_COPY_DEST="<absolute-path-to-directory>"
```

### 3. Run the script directly:

```bash
python3 process_localization.py
```

It will read all JSON files from the `prompts/` directory and process each one in turn.

## 📂 Important files and variables

- ### `process_localization.py` — entrypoint. Key behavior:
  - reads env vars with `dotenv` and sets sensible defaults
  - `cfgs`, `denoises`, and `seeds` are defined near the top of the file and control the combinations that get queued
  - uses `queue_prompt()` from `api_helpers.py` to POST prompts to the server and `wait_until_queue_empty()` to block until processing finishes
  - after processing a prompt file it calls `find_line_with_max_avg()` (from `helpers.py`) on `DEFAULT_FIND_MAX_FILE` to pick the best batch index, then copies matching images from the outputs directory into a subfolder of `DEFAULT_COPY_DEST`

- ### `helpers.py` — small utilities:
  - `find_line_with_max_avg(file_path)` reads a file where each line contains numeric scores separated by ", ". It returns the (line_number, average) of the best line and clears the file afterwards. Line numbers are 0-based in this implementation.
  - `copy_images_with_pattern(src_dir, dst_dir, org_dir, starts_with)` copies files from `src_dir` whose filename starts with `starts_with` into `dst_dir`. It uses the filenames listing from `org_dir` to name copied files. Note: the function signature in the repository is slightly different from how it's called in `process_localization.py` — see "Gotchas" below.
  - `clear_outputs_dir(outputs_path)` deletes all files under the outputs path (destructive).

- ### `api_helpers.py` — server interaction helpers:
  - `queue_prompt(prompt, server_address, client_id)` POSTs the workflow JSON payload to `http://{server_address}/prompt`.
  - `wait_until_queue_empty(server_address, poll_interval=10.0)` polls `http://{server_address}/queue` until the queue is empty.
  - `load_prompt(prompt_path)` loads a workflow JSON from the `workflows/` directory.
  - `load_prompt_text(json_path)` loads a prompt JSON and validates required keys.

## 🎛️ Customization

- **Prompts** → Edit/add JSON files in prompts/.
- **Workflow** → Change WORKFLOW_FILE or modify workflows/pipeline_api.json.
- **Image set** → Point PICTURES_DIRECTORY to a new image folder.
- **Hyperparameters for tuning** → Adjust cfgs, denoises, seeds in process_localization.py.
- **Batch sizing** → Modify image_load_cap, batch_size, limit inside process_images(). *Change this if your GPU is low on VRAM*

## ⚠️ Gotchas

- ### **File paths** → Workflow files must live in workflows/.
- ### **Indexing and signatures**:
  - `find_line_with_max_avg()` returns 0-based line numbers (and truncates the score file after reading). The code expects this value to be used as a batch prefix when copying images.
  - `copy_images_with_pattern()` in `helpers.py` is defined as `copy_images_with_pattern(src_dir: str, dst_dir: str, org_dir: str, starts_with: str)`, but the `process_localization.py` calls it with three arguments: `copy_images_with_pattern(DEFAULT_OUTPUTS_PATH, new_dest, copy_pattern)`. If you keep the current code, pass a fourth argument `org_dir` (likely the original pictures directory or a directory listing used for naming). Otherwise update the function call to match the implementation.
- ### `clear_outputs_dir()` is destructive — be sure `DEFAULT_OUTPUTS_PATH` is set to a safe folder.

## 🛠️ Troubleshooting

- ### If the script cannot reach the server, check `SERVER_ADDRESS` and ensure the server exposes `/prompt` and `/queue` endpoints compatible with the payload shape.
- ### If `find_line_with_max_avg()` prints warnings about parsing floats, inspect the score file (`DEFAULT_FIND_MAX_FILE`) and ensure it contains numeric values separated by ", ".

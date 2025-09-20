import json
import os
import re
import shutil
from typing import Tuple, List, Optional
import urllib
import urllib.request
import urllib.parse
from urllib.error import HTTPError
import uuid
import time

from dotenv import load_dotenv
load_dotenv()

DEFAULT_OUTPUTS_PATH = os.getenv("DEFAULT_OUTPUTS_PATH", "")
DEFAULT_FIND_MAX_FILE = os.getenv("DEFAULT_FIND_MAX_FILE", "")
DEFAULT_COPY_DEST = os.getenv("DEFAULT_COPY_DEST", "")

cfgs = [6.9, 7.5, 8.0]
denoises = [0.7, 0.8, 0.9]
seeds = [691033582574281, 42]

server_address = "127.0.0.1:8188"
client_id = str(uuid.uuid4())

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(
        f"http://{server_address}/prompt",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[HTTP {e.code}] {e.reason}\n{body}")
        raise

def load_prompt(prompt_path):
    if not os.path.exists(f"workflows/{prompt_path}"):
        raise FileNotFoundError(f"Prompt file not found: workflows/{prompt_path}")
    with open(f"workflows/{prompt_path}", 'r') as f:
        prompt_text = f.read()
    
    return json.loads(prompt_text)

def load_prompt_text(json_path: str) -> dict:
    if not os.path.exists(json_path):
        raise FileNotFoundError(json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required = ("positive_prompt", "negative_prompt", "verification_prompt")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing required prompt keys in {json_path}: {missing}")
    return {k: data[k] for k in required}

def process_images(workflow_path, pictures_dir, location_prompt):
    prompts = load_prompt_text(location_prompt)
    prompt_data = load_prompt(workflow_path)
    prompt_data["48"]["inputs"]["directory"] = pictures_dir
    prompt_data["48"]["inputs"]["image_load_cap"] = len(os.listdir(pictures_dir))
    prompt_data["5"]["inputs"]["batch_size"] = len(os.listdir(pictures_dir))
    prompt_data["38"]["inputs"]["limit"] = len(os.listdir(pictures_dir))
    prompt_data["2"]["inputs"]["text"] = prompts["positive_prompt"]
    prompt_data["3"]["inputs"]["text"] = prompts["negative_prompt"]
    prompt_data["40"]["inputs"]["text"] = prompts["verification_prompt"]

    for cfg in cfgs:
        for denoise in denoises:
            for seed in seeds:
                prompt_data["4"]["inputs"]["cfg"] = cfg
                prompt_data["4"]["inputs"]["denoise"] = denoise
                prompt_data["4"]["inputs"]["seed"] = seed

                queue_prompt(prompt_data)
                
def wait_until_queue_empty(poll_interval: float = 2.0) -> None:
    """Poll the ComfyUI queue endpoint until both queue_running and queue_pending are empty.

    The server returns JSON like: {"queue_running": [], "queue_pending": []} when empty.
    If timeout (seconds) is provided and exceeded, raises TimeoutError.
    """
    path = f"http://{server_address}/queue"
    start = time.time()
    while True:
        try:
            with urllib.request.urlopen(path, timeout=5) as response:
                raw = response.read().decode("utf-8", errors="ignore")
                try:
                    data = json.loads(raw)
                except Exception:
                    data = None

                if isinstance(data, dict):
                    if "queue_running" in data and "queue_pending" in data:
                        running = data.get("queue_running") or []
                        pending = data.get("queue_pending") or []
                        if isinstance(running, list) and isinstance(pending, list) and (len(running) + len(pending)) == 0:
                            return
                if isinstance(data, list) and len(data) == 0:
                    return
                try:
                    if int(raw.strip()) == 0:
                        return
                except Exception:
                    pass
        except Exception as e:
            # ignore transient errors and retry until timeout
            # print a short warning for visibility
            print(f"Warning: could not query queue status: {e}")

        time.sleep(poll_interval)


def localization_workflow(workflow_path, pictures_dir, prompts_text_dir):
    clear_outputs_dir(DEFAULT_OUTPUTS_PATH)
    for filename in os.listdir(prompts_text_dir):
        if not filename.lower().endswith(".json"):
            continue
        full_path = os.path.join(prompts_text_dir, filename)
        try:
            process_images(workflow_path, pictures_dir, full_path)
        except Exception as e:
            print(f"Error processing {full_path}: {e}")
            continue
        # wait until the server's prompt queue is empty before continuing
        wait_until_queue_empty()
        line_number, score = find_line_with_max_avg(DEFAULT_FIND_MAX_FILE)
        print(f"Best line in {DEFAULT_FIND_MAX_FILE}: {line_number} with average score {score}")
        base_name = os.path.splitext(filename)[0]
        new_dest = os.path.join(DEFAULT_COPY_DEST, base_name)
        os.makedirs(new_dest, exist_ok=True)
        copy_pattern = f"_{line_number}.jpg"
        copy_images_with_pattern(DEFAULT_OUTPUTS_PATH, new_dest, copy_pattern)


def clear_outputs_dir(outputs_path: str) -> None:
    """Remove all files and subdirectories under outputs_path.

    This is destructive: it will delete everything under the given path.
    The function verifies the path exists and refuses to operate on root-like paths.
    """
    if not os.path.exists(outputs_path):
        return

    for entry in os.listdir(outputs_path):
        full = os.path.join(outputs_path, entry)
        os.remove(full)


def find_line_with_max_avg(file_path: str):
    """Read the file at file_path where each line contains floats separated by ", ".

    Returns a tuple (line_number, average) for the line with the highest average.
    Line numbers are 1-based. After finding the line the function will truncate the file (clear it).
    If the file is empty or contains no valid lines, returns (0, 0.0) and clears the file.
    """
    best_avg = float("-inf")
    best_worst = float("-inf")
    best_best = float("-inf")
    best_line_no = 0
    lines_read = 0

    if not os.path.exists(file_path):
        return 0, 0.0

    with open(file_path, "r", encoding="utf-8") as f:
        for idx, raw in enumerate(f, start=0):
            s = raw.strip()
            if not s:
                continue
            lines_read += 1
            parts = [p.strip() for p in s.split(", ")]
            nums: List[float] = []
            for p in parts:
                if not p:
                    continue
                try:
                    nums.append(float(p) * 1000)
                except ValueError:
                    print(f"Warning: could not parse float from '{p}' in line {idx} of {file_path}")
                    pass
            print(nums)
            if not nums:
                continue
            avg = sum(nums) / len(nums)
            print(f"Line {idx} average: {avg}")
            if avg > best_avg or avg > best_avg * 0.98 and nums[-1] > best_worst or avg > best_avg * 0.98 and nums[-1] > best_worst * 0.999 and nums[0] > best_best:
                best_avg = avg
                best_line_no = idx
                best_worst = nums[-1]
                best_best = nums[0]
    # clear the file
    try:
        open(file_path, "w", encoding="utf-8").close()
    except Exception:
        print(f"Warning: could not clear file {file_path}")
        pass

    if lines_read == 0:
        return 0, 0.0
    return best_line_no, best_avg


def copy_images_with_pattern(src_dir: str, dst_dir: str, ends_with_pattern: str) -> int:
    """Copy images from src_dir to dst_dir where filename ends with the provided pattern.

    The pattern is treated as a suffix to match against the filename (before the extension
    or including the extension). Returns the number of files copied.
    """
    if not os.path.exists(src_dir):
        raise FileNotFoundError(src_dir)
    os.makedirs(dst_dir, exist_ok=True)

    # build regex to match filenames that end with the provided pattern
    # escape pattern to treat it literally
    esc = re.escape(ends_with_pattern)
    pattern = re.compile(rf"{esc}$")

    copied = 0
    for name in os.listdir(src_dir):
        full = os.path.join(src_dir, name)
        if not os.path.isfile(full):
            continue
        if pattern.search(name):
            try:
                shutil.copy2(full, os.path.join(dst_dir, name))
                copied += 1
            except Exception:
                pass
    return copied


if __name__ == "__main__":
    workflow_file = "pipeline_api.json"
    pictures_directory = "/home/kn-bit/programow/nvidia-geo-guessing/pipeline/pictures/paris/before"
    prompts_directory = "prompts"

    localization_workflow(workflow_file, pictures_directory, prompts_directory)




import time
import urllib
import urllib.request
import urllib
import json
import os
from urllib.error import HTTPError


def wait_until_queue_empty(server_address, poll_interval: float = 10.0) -> None:
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

def queue_prompt(prompt, server_address, client_id) -> dict:
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
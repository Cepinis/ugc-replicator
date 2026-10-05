"""kie.ai client: file upload, task create/poll, chat. Used for Seedance, GPT Image 2 and the headline model."""
import json
import os
import time
from pathlib import Path

import requests

API = "https://api.kie.ai"


def _headers():
    return {"Authorization": f"Bearer {os.environ['KIE_API_KEY']}"}


def upload(path):
    """Upload a local file; kie.ai keeps it for 3 days and returns a public URL."""
    with open(path, "rb") as f:
        r = requests.post(f"{API}/api/file-stream-upload", headers=_headers(),
                          files={"file": (Path(path).name, f)}, data={"uploadPath": "ugc-replicator"},
                          timeout=300)
    r.raise_for_status()
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"kie.ai upload failed: {body}")
    return body["data"]["downloadUrl"]


def download(url, out_path):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def run_task(model, inputs, poll_s=10, timeout_s=1800):
    """Create a market task and wait for it. Returns (result_urls, task_data)."""
    r = requests.post(f"{API}/api/v1/jobs/createTask", headers=_headers(), timeout=60,
                      json={"model": model, "input": inputs})
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 200:
        raise RuntimeError(f"kie.ai createTask failed: {body}")
    task_id = body["data"]["taskId"]
    print(f"  {model} task {task_id}")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        r = requests.get(f"{API}/api/v1/jobs/recordInfo", headers=_headers(),
                         params={"taskId": task_id}, timeout=60)
        r.raise_for_status()
        data = r.json()["data"]
        if data["state"] == "success":
            return json.loads(data["resultJson"])["resultUrls"], data
        if data["state"] == "fail":
            raise RuntimeError(f"{model} failed: {data.get('failCode')} {data.get('failMsg')}")
        print(f"  ...{data['state']} {data.get('progress') or ''}")
    raise TimeoutError(f"{model} task {task_id} did not finish in {timeout_s}s")


def chat(model, text, image_url=None):
    """One-shot text (+ optional image) prompt to a GPT model on kie.ai. Returns the reply text."""
    content = [{"type": "input_text", "text": text}]
    if image_url:
        content.append({"type": "input_image", "image_url": image_url})
    r = requests.post(f"{API}/codex/v1/responses", headers=_headers(), timeout=300, json={
        "model": model, "stream": False, "input": [{"role": "user", "content": content}],
    })
    r.raise_for_status()
    body = r.json()
    return "".join(c.get("text", "") for o in body.get("output", []) if o.get("type") == "message"
                   for c in o.get("content", []) if c.get("type") == "output_text")

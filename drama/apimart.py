"""Apimart client: one API key for Claude (writer/director), GPT Image 2 (character cards) and Seedance 2.5 (clips)."""
import json
import os
import re
import time
from pathlib import Path

import requests

API = "https://api.apimart.ai/v1"


def _headers():
    return {"Authorization": f"Bearer {os.environ['APIMART_API_KEY']}"}


def chat(system, user, model=None, max_tokens=16000):
    """One-shot Claude call. Returns the reply text."""
    model = model or os.environ.get("CLAUDE_MODEL", "claude-fable-5")
    r = requests.post(f"{API}/chat/completions", headers=_headers(), timeout=900, json={
        "model": model, "stream": False, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    })
    if r.status_code != 200:
        raise RuntimeError(f"Claude call failed ({r.status_code}): {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"]


def chat_json(system, user, **kw):
    """Claude call that must answer with one JSON object."""
    text = chat(system, user + "\n\nAnswer with ONE JSON object only, no other text.", **kw)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"Claude did not return JSON: {text[:500]}")
    return json.loads(m.group(0))


def upload(path):
    """Upload a local image and get a public URL usable as a reference."""
    with open(path, "rb") as f:
        r = requests.post(f"{API}/uploads/images", headers=_headers(),
                          files={"file": (Path(path).name, f)}, timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"Upload failed ({r.status_code}): {r.text[:500]}")
    body = r.json()
    url = body.get("url") or (body.get("data") or {}).get("url")
    if not url:
        raise RuntimeError(f"Upload returned no URL: {body}")
    return url


def download(url, out_path):
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _first_url(obj):
    """Find the first http(s) URL anywhere in a task result."""
    if isinstance(obj, str):
        return obj if obj.startswith("http") else None
    if isinstance(obj, dict):
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            u = _first_url(v)
            if u:
                return u
    return None


def _submit(endpoint, payload):
    r = requests.post(f"{API}/{endpoint}", headers=_headers(), json=payload, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"{payload.get('model')} submit failed ({r.status_code}): {r.text[:500]}")
    body = r.json()
    data = body.get("data")
    task = (data[0] if isinstance(data, list) else data or {}).get("task_id")
    if not task:
        raise RuntimeError(f"{payload.get('model')} submit returned no task: {body}")
    return task


def wait(task_id, log=print, poll_s=10, timeout_s=3600):
    """Poll a task until it is done. Returns (result_url, task_data)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        r = requests.get(f"{API}/tasks/{task_id}", headers=_headers(), timeout=60)
        if r.status_code != 200:
            log(f"  status check failed ({r.status_code}), retrying")
            continue
        data = r.json().get("data") or {}
        status = data.get("status")
        if status == "completed":
            url = _first_url(data.get("result"))
            if not url:
                raise RuntimeError(f"Task {task_id} finished without a file: {data}")
            return url, data
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"Task {task_id} failed: {data.get('error') or data.get('fail_reason') or data}")
        log(f"  ...{status} {data.get('progress') or ''}")
    raise TimeoutError(f"Task {task_id} did not finish in {timeout_s}s")


def image(prompt, out_path, refs=(), size="2:3", log=print):
    """GPT Image 2. refs = public image URLs. Saves the image and returns the task data."""
    payload = {"model": "gpt-image-2", "prompt": prompt, "size": size, "n": 1, "resolution": "2k"}
    if refs:
        payload["image_urls"] = list(refs)
    task = _submit("images/generations", payload)
    log(f"  image task {task}")
    url, data = wait(task, log, poll_s=5)
    download(url, out_path)
    return data


def video(prompt, out_path, duration, images=(), resolution="720p", log=print):
    """Seedance 2.5. images = reference image URLs, referred to as @image1..N in the prompt. Saves the clip."""
    payload = {
        "model": "seedance-2.5", "prompt": prompt, "size": "9:16", "resolution": resolution,
        "duration": int(duration), "generate_audio": True, "watermark": False,
    }
    if images:
        payload["image_urls"] = list(images)
    task = _submit("videos/generations", payload)
    log(f"  seedance task {task}")
    url, data = wait(task, log)
    download(url, out_path)
    return data

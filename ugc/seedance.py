"""Seedance 2.5 video edit through kie.ai."""
import json
import os
import time
from pathlib import Path

import requests

API = "https://api.kie.ai"
MODEL = "bytedance/seedance-2-5"


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


def build_prompt(new_headline, old_headline=None):
    old = f' (currently "{old_headline}")' if old_headline else ""
    return (
        "Edit @Video1. Replace the person in the video with the person from @Image1: their face, hair, skin "
        "and clothing. Keep everything else exactly the same: head and body motion, facial expressions, "
        "mouth and lip movements, timing, camera framing, background and lighting. It must still look like "
        "a casual front-camera phone selfie video.\n"
        f"Also replace the headline text at the top of the video{old} with exactly this text: "
        f'"{new_headline}". Keep the same font, size, color, background box and position. '
        "Do not add any other text."
    )


def edit(hook_path, avatar_path, prompt, out_path, resolution="720p", poll_s=10, timeout_s=1800):
    video_url = upload(hook_path)
    image_url = upload(avatar_path)
    r = requests.post(f"{API}/api/v1/jobs/createTask", headers=_headers(), timeout=60, json={
        "model": MODEL,
        "input": {
            "prompt": prompt,
            "reference_video_urls": [video_url],
            "reference_image_urls": [image_url],
            "resolution": resolution,
            "aspect_ratio": "adaptive",
            "duration": -1,  # video edit: follow the input length
            "generate_audio": False,  # we put the original audio back ourselves
        },
    })
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 200:
        raise RuntimeError(f"kie.ai createTask failed: {body}")
    task_id = body["data"]["taskId"]
    print(f"  seedance task {task_id}")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        r = requests.get(f"{API}/api/v1/jobs/recordInfo", headers=_headers(),
                         params={"taskId": task_id}, timeout=60)
        r.raise_for_status()
        data = r.json()["data"]
        if data["state"] == "success":
            url = json.loads(data["resultJson"])["resultUrls"][0]
            with requests.get(url, stream=True, timeout=300) as dl:
                dl.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in dl.iter_content(1 << 20):
                        f.write(chunk)
            return {"task_id": task_id, "credits": data.get("creditsConsumed")}
        if data["state"] == "fail":
            raise RuntimeError(f"Seedance failed: {data.get('failCode')} {data.get('failMsg')}")
        print(f"  ...{data['state']} {data.get('progress') or ''}")
    raise TimeoutError(f"Seedance task {task_id} did not finish in {timeout_s}s")

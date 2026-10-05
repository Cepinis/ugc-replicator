"""OpenAI calls: generate a new avatar image and pick/generate a headline."""
import base64
import json
import os
import random
from pathlib import Path

from openai import OpenAI

IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1024x1536")
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5-mini")

# Rough variety so every video doesn't get the same person.
PEOPLE = [
    "a woman in her early 20s", "a woman in her late 20s", "a woman in her 30s", "a woman in her 40s",
    "a man in his early 20s", "a man in his late 20s", "a man in his 30s", "a man in his 40s",
]
LOOKS = [
    "messy bun, no makeup", "hoodie, slightly tired eyes", "plain t-shirt, hair a bit greasy",
    "glasses, oversized sweater", "baseball cap, stubble", "headphones around neck",
    "hair tied back, light freckles", "work-from-home look, cardigan",
]

client = OpenAI()


def make_avatar(frame_path, out_path, person=None):
    """Re-imagine the hook's frame with a different, ordinary-looking person in the same setup."""
    person = person or f"{random.choice(PEOPLE)}, {random.choice(LOOKS)}"
    prompt = (
        f"Replace the person in this phone selfie with a completely different person: {person}. "
        "Ordinary, real, not a model: normal skin texture, pores, slight blemishes, unflattering phone lighting, "
        "casual everyday clothes. Keep the same pose, camera angle, framing, distance from the front camera "
        "and a similar room/background. Shot on an iPhone front camera, slightly soft, no beauty filter. "
        "Remove all text and captions from the image."
    )
    with open(frame_path, "rb") as f:
        res = client.images.edit(model=IMAGE_MODEL, image=f, prompt=prompt, size=IMAGE_SIZE)
    Path(out_path).write_bytes(base64.b64decode(res.data[0].b64_json))
    return person


def _lines(path):
    p = Path(path)
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]


def headline(frame_path, examples_file, winners_file, reuse=False):
    """Read the original headline from the frame, then reuse a winner or write a new one.

    Returns (original, new).
    """
    examples = _lines(examples_file)
    winners = _lines(winners_file)
    img = base64.b64encode(Path(frame_path).read_bytes()).decode()
    task = (
        "This is a frame from a TikTok UGC hook video. Read the headline text overlaid at the top exactly.\n"
        "Then write ONE new headline for a similar video: same vibe, length and casing style, "
        "but different wording and angle. Do not copy the original or the examples.\n"
    )
    if examples or winners:
        task += "Headlines in the style we want:\n" + "\n".join(f"- {h}" for h in (winners + examples)[:60]) + "\n"
    task += 'Reply with JSON only: {"original": "...", "new": "..."}'
    res = client.chat.completions.create(
        model=TEXT_MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": task},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}},
        ]}],
    )
    data = json.loads(res.choices[0].message.content)
    new = random.choice(winners) if reuse and winners else data["new"]
    return data.get("original") or None, new

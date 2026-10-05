"""Seedance 2.5 video edit through kie.ai."""
from . import kie

MODEL = "bytedance/seedance-2-5"


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


def edit(hook_path, avatar_path, prompt, out_path, resolution="720p"):
    urls, data = kie.run_task(MODEL, {
        "prompt": prompt,
        "reference_video_urls": [kie.upload(hook_path)],
        "reference_image_urls": [kie.upload(avatar_path)],
        "resolution": resolution,
        "aspect_ratio": "adaptive",
        "duration": -1,  # video edit: follow the input length
        "generate_audio": False,  # we put the original audio back ourselves
    })
    kie.download(urls[0], out_path)
    return {"task_id": data["taskId"], "credits": data.get("creditsConsumed")}

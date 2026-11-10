"""Small local page to drive the pipeline: premise -> script -> characters -> shot list -> clips -> final."""
import html
import json
import threading
import traceback
from pathlib import Path

from flask import Flask, abort, redirect, request, send_from_directory

from . import pipeline as P

app = Flask(__name__)
BUSY = {}  # project name -> what is running


def background(name, label, fn, *args):
    if BUSY.get(name):
        return
    BUSY[name] = label
    log = P.logger(name)

    def go():
        try:
            fn(*args)
        except Exception as e:  # show the problem on the page instead of dying silently
            log(f"ERROR in {label}: {e}")
            traceback.print_exc()
        finally:
            BUSY.pop(name, None)
    threading.Thread(target=go, daemon=True).start()


CSS = """
body{font:15px/1.45 -apple-system,system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222;background:#fafafa}
h1{font-size:22px} h2{font-size:18px;margin-top:32px;border-bottom:1px solid #ddd;padding-bottom:4px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:14px;margin:10px 0}
textarea,input[type=text],input[type=number]{width:100%;box-sizing:border-box;font:inherit;padding:8px;border:1px solid #ccc;border-radius:6px}
textarea.prompt{min-height:180px;font:13px/1.4 ui-monospace,monospace}
button{font:inherit;padding:7px 14px;border-radius:6px;border:1px solid #888;background:#fff;cursor:pointer;margin:4px 4px 4px 0}
button.go{background:#111;color:#fff;border-color:#111}
.row{display:flex;gap:12px;flex-wrap:wrap} .row img{height:220px;border-radius:6px;background:#eee}
video{height:420px;border-radius:8px;background:#000}
.muted{color:#777;font-size:13px} .busy{background:#fff4cc;padding:8px 12px;border-radius:6px}
pre.log{background:#111;color:#ddd;padding:10px;border-radius:6px;max-height:220px;overflow:auto;font-size:12px}
.err{color:#b00}
"""


def page(title, body, refresh=False):
    meta = '<meta http-equiv="refresh" content="5">' if refresh else ""
    return f"<!doctype html><html><head><meta charset=utf-8><title>{html.escape(title)}</title>{meta}<style>{CSS}</style></head><body>{body}</body></html>"


def esc(s):
    return html.escape(str(s or ""))


def form(action, label, extra="", cls=""):
    return f'<form method=post action="{action}" style="display:inline">{extra}<button class="{cls}">{label}</button></form>'


@app.get("/")
def home():
    P.PROJECTS.mkdir(exist_ok=True)
    items = sorted((d for d in P.PROJECTS.iterdir() if (d / "premise.json").exists()),
                   key=lambda d: d.stat().st_mtime, reverse=True)
    rows = "".join(
        f'<div class=card><a href="/p/{d.name}"><b>{esc((P.read(d.name, "script.json") or {}).get("title") or d.name)}</b></a>'
        f'<div class=muted>{esc(P.read(d.name, "premise.json")["premise"][:200])}</div></div>' for d in items)
    body = f"""<h1>Drama ads</h1>
<div class=card><form method=post action="/new" enctype="multipart/form-data">
<p><b>Premise</b><br><textarea name=premise rows=4 placeholder="e.g. A nurse gets humiliated by her rich mother-in-law at a family dinner, then reveals she secretly owns the hospital."></textarea></p>
<p><b>Product</b> (what the ad sells, one or two sentences)<br><input type=text name=product></p>
<p><b>Product image</b> (optional: screenshot, logo or photo)<br><input type=file name=product_image accept="image/*"></p>
<p><b>Length in seconds</b><br><input type=number name=seconds value=45 min=10 max=180></p>
<button class=go>Write the script</button></form></div>
<h2>Your ads</h2>{rows or '<p class=muted>None yet.</p>'}"""
    return page("Drama ads", body)


@app.post("/new")
def new():
    premise = request.form.get("premise", "").strip()
    if not premise:
        return redirect("/")
    name = P.new_project(premise, request.form.get("product", "").strip(), request.form.get("seconds") or 45)
    f = request.files.get("product_image")
    if f and f.filename:
        f.save(P.pdir(name) / "product.png")
    background(name, "writing the script", P.write_script, name)
    return redirect(f"/p/{name}")


@app.get("/p/<name>")
def project(name):
    if not (P.pdir(name) / "premise.json").exists():
        abort(404)
    prem, script, plan = P.read(name, "premise.json"), P.read(name, "script.json"), P.read(name, "clips.json")
    busy = BUSY.get(name)
    u = f"/p/{name}"
    out = [f'<p><a href="/">&larr; all ads</a></p><h1>{esc((script or {}).get("title") or name)}</h1>',
           f'<div class=card><b>Premise:</b> {esc(prem["premise"])}<br><b>Product:</b> {esc(prem["product"]) or "-"} · <b>Length:</b> {prem["seconds"]}s</div>']
    if busy:
        out.append(f'<p class=busy>Working: {esc(busy)}… (this page refreshes by itself)</p>')

    # 1. script
    out.append("<h2>1. Script</h2>")
    if script:
        out.append(f'<p><i>{esc(script.get("logline"))}</i></p>')
        out.append("<div class=card><b>Cast</b><ul>" + "".join(
            f'<li><b>{esc(c["name"])}</b> ({esc(c.get("role"))}): {esc(c["look"])} <span class=muted>Voice: {esc(c.get("voice"))}</span></li>'
            for c in script.get("characters", [])) + "</ul></div>")
        for b in script.get("beats", []):
            lines = "".join(f'<div>&nbsp;&nbsp;<b>{esc(d["speaker"])}:</b> "{esc(d["line"])}"</div>' for d in b.get("dialogue", []))
            out.append(f'<div class=card><b>Beat {b.get("n")}: {esc(b.get("job"))}</b><div>{esc(b.get("what_happens"))}</div>{lines}</div>')
        out.append(f'<form method=post action="{u}/script"><textarea name=notes rows=2 placeholder="Notes for a rewrite (optional), e.g. make the villain nastier, shorter ending"></textarea><button>Rewrite the script</button></form>')
    else:
        out.append(form(f"{u}/script", "Write the script", cls="go"))

    # 2. characters
    if script:
        out.append("<h2>2. Character cards</h2>")
        for c in script.get("characters", []):
            d = P.char_dir(name, c["name"])
            imgs = "".join(f'<img src="/f/{name}/characters/{d.name}/{v}.png?{(d / f"{v}.png").stat().st_mtime_ns}" title="{v}">'
                           for v in ("front", "side", "back") if (d / f"{v}.png").exists())
            out.append(f'<div class=card><b>{esc(c["name"])}</b><div class=row>{imgs or "<span class=muted>not made yet</span>"}</div>'
                       + form(f"{u}/character", "Make again" if imgs else "Make", f'<input type=hidden name=char value="{esc(c["name"])}">') + "</div>")
        if (P.pdir(name) / "product.png").exists():
            out.append(f'<div class=card><b>Product</b><div class=row><img src="/f/{name}/product.png"></div></div>')
        out.append(form(f"{u}/characters", "Make all missing character cards", cls="go"))

    # 3. shot list
    if script:
        out.append("<h2>3. Director: shot list</h2>")
        if plan:
            total = sum(c["duration"] for c in plan["clips"])
            out.append(f'<p class=muted>{len(plan["clips"])} clips, {total}s total. You can edit any prompt and press Save.</p>')
            for c in plan["clips"]:
                f = P.pdir(name) / "clips" / f'{c["n"]:02d}.mp4'
                vid = f'<video controls src="/f/{name}/clips/{f.name}?{f.stat().st_mtime_ns}"></video>' if f.exists() else ""
                out.append(f'''<div class=card><b>Clip {c["n"]}</b> · {c["duration"]}s · {esc(c.get("kind"))} · {esc(", ".join(c.get("characters", [])))}{" · product" if c.get("uses_product") else ""}
<div class=row><div style="flex:1;min-width:320px"><form method=post action="{u}/clip/{c["n"]}/save">
<textarea class=prompt name=prompt>{esc(c["prompt"])}</textarea>
Seconds <input type=number name=duration value={c["duration"]} min=4 max=15 style="width:80px"> <button>Save</button></form>
{form(f"{u}/clip/{c['n']}/make", "Make this clip again" if vid else "Make this clip")}</div>{vid}</div></div>''')
            out.append(f'<form method=post action="{u}/direct"><textarea name=notes rows=2 placeholder="Notes for the director (optional), e.g. more close-ups, faster start"></textarea><button>Redo the shot list</button></form>')
        else:
            out.append(form(f"{u}/direct", "Direct it", cls="go"))

    # 4. video
    if plan:
        out.append("<h2>4. Video</h2>")
        out.append(form(f"{u}/clips", "Make all missing clips", cls="go") + form(f"{u}/join", "Join clips into final video"))
        out.append(form(f"{u}/all", "Do everything that's missing, then join"))
        final = P.pdir(name) / "final.mp4"
        if final.exists():
            out.append(f'<div class=card><b>Final video</b><br><video controls src="/f/{name}/final.mp4?{final.stat().st_mtime_ns}"></video>'
                       f'<div class=muted>Saved in projects/{name}/final.mp4</div></div>')

    log = P.pdir(name) / "log.txt"
    if log.exists():
        tail = log.read_text().splitlines()[-25:]
        out.append("<h2>Log</h2><pre class=log>" + esc("\n".join(tail)) + "</pre>")
    return page(name, "".join(out), refresh=bool(busy))


@app.post("/p/<name>/<action>")
def act(name, action):
    f = request.form
    jobs = {
        "script": ("writing the script", P.write_script, name, f.get("notes", "")),
        "character": (f"making {f.get('char')}", P.make_characters, name, f.get("char")),
        "characters": ("making character cards", P.make_characters, name),
        "direct": ("directing", P.direct, name, f.get("notes", "")),
        "clips": ("making clips", P.make_clips, name),
        "join": ("joining", P.join, name),
        "all": ("making the whole video", P.run_all, name),
    }
    if action not in jobs:
        abort(404)
    label, fn, *args = jobs[action]
    background(name, label, fn, *args)
    return redirect(f"/p/{name}")


@app.post("/p/<name>/clip/<int:n>/<action>")
def clip_action(name, n, action):
    if action == "save":
        plan = P.read(name, "clips.json")
        for c in plan["clips"]:
            if c["n"] == n:
                c["prompt"] = request.form.get("prompt", c["prompt"])
                c["duration"] = max(4, min(15, int(request.form.get("duration") or c["duration"])))
        P.write(name, "clips.json", plan)
    elif action == "make":
        background(name, f"making clip {n}", P.make_clip, name, n)
    return redirect(f"/p/{name}")


@app.get("/f/<name>/<path:rel>")
def files(name, rel):
    return send_from_directory(P.pdir(name), rel)


def main(port=5055):
    import webbrowser
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(port=port, debug=False)

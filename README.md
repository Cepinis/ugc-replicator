# Drama ads + UGC replicator

## Drama ads (new)

Premise in, finished 9:16 micro-drama ad out. Double-click **Start Drama Ads.command**, and a page opens in the browser.

1. **Script**: Claude writes the story beat by beat (hook, villain, proof, product, payoff, CTA). Rewrite with notes until it's right.
2. **Character cards**: GPT Image 2 makes a front, side and back image of every character (plus your product image, if given).
3. **Director**: Claude splits the script into clips of exact whole-second lengths, adds b-roll, and writes a second-by-second prompt per clip. Every prompt can be edited on the page.
4. **Clips**: Seedance 2.5 makes each clip with sound and dialogue; character cards are attached as `@image1..N` so faces stay consistent.
5. **Join**: ffmpeg glues the clips in order, nothing trimmed. Result: `projects/<name>/final.mp4`.

All AI calls go through Apimart with one key: put `APIMART_API_KEY=...` in `.env`.
The writer, director and character prompts live in `drama/prompts/` if you want to tweak the style.
No clicking: `python -m drama make "premise" --product "..." --seconds 45`.

---

## UGC video replicator (old tool)

Takes TikTok videos shaped like "≤5s face-cam hook with a headline, then phone-filming-phone app showcase",
swaps the person and the headline in the hook, and glues the original showcase back on. 9:16 throughout.

## Setup (macOS)

```bash
brew install ffmpeg python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in KIE_API_KEY (and APIFY_TOKEN for fetch)
```

## Use

```bash
# 1. download videos (repeat --profile / --hashtag as needed)
python -m ugc fetch --profile someuser --hashtag sometrend --limit 10

# 2. optional: check where each hook ends
python -m ugc cut inputs/*.mp4

# 3. make new versions
python -m ugc run inputs/*.mp4
python -m ugc run inputs/one.mp4 --cut 3.4 --headline "my exact headline"
python -m ugc run inputs/*.mp4 --reuse        # reuse a headline from headlines/winners.txt
```

Each video gets a folder in `outputs/` with `final.mp4` plus the in-between files
(`hook_720.mp4`, `avatar.png`, `hook_new.mp4`) and `info.json` (cut, headlines, prompt, Seedance task id).

## Headlines

- `headlines/examples.txt`: headlines in the style you like. New headlines are written in that style.
- `headlines/winners.txt`: headlines that performed. `--reuse` picks one of these instead of writing a new one.

## How it works

1. **fetch**: Apify `clockworks/tiktok-scraper` downloads the mp4s.
2. **cut**: ffmpeg scene detection; the first hard cut after 0.8s (within the first 8s) is the hook end.
   Override with `--cut`, or tune `--threshold` (default 0.3; lower finds softer cuts).
3. **headline**: a GPT model on kie.ai reads the current headline off a hook frame and writes a new one.
4. **avatar**: GPT Image 2 on kie.ai redraws a hook frame with a different, ordinary-looking person.
5. **swap**: Seedance 2.5 on kie.ai edits the hook: new person from the avatar image, new headline, same motion.
6. **join**: ffmpeg puts the new hook (with the original hook audio) in front of the original showcase, 1080x1920 @ 30fps.

The Seedance prompt lives in `ugc/seedance.py` (`build_prompt`) and the avatar prompt in `ugc/ai.py` (`make_avatar`);
those are the two places to tweak when results look off.

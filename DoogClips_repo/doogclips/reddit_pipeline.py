import os
import json
import random
import time
import re
import subprocess
import requests
import asyncio
import edge_tts
import cv2
import numpy as np
from io import BytesIO
from PIL import Image, ImageDraw
from typing import List, Dict, Optional

from doogclips.pipeline import get_gameplay_video, get_bgm_path, get_bg_url, DOWNLOADS_DIR, EXPORTS_DIR, TEMP_DIR, GAMEPLAY_URLS
from doogclips.transcriber import transcribe
from doogclips.subtitle_renderer import render_subtitle_frame, _get_font, _wrap_words, _draw_part_overlay
from doogclips.utils.paths import resolve_path

try:
    from .utils.qwen_tts import QwenTTSManager
    HAS_QWEN = True
except ImportError:
    HAS_QWEN = False

HISTORY_FILE = resolve_path("doogclips/data/history.json")

_REDDIT_UI_ICONS = None

def _load_reddit_ui_icons():
    global _REDDIT_UI_ICONS
    if _REDDIT_UI_ICONS is not None:
        return _REDDIT_UI_ICONS
    base = resolve_path(os.path.join("assets", "icons", "reddit"))
    def load(name):
        try:
            path = os.path.join(base, name)
            if os.path.exists(path):
                return Image.open(path).convert("RGBA")
        except:
            return None
        return None
    _REDDIT_UI_ICONS = {
        "upvote": load("upvote.png"),
        "downvote": load("downvote.png"),
        "comment": load("comment.png"),
        "award": load("award.png"),
        "share": load("share.png"),
        "rslash": load("rslash.png"),
    }
    return _REDDIT_UI_ICONS

async def _gen_audio_async(text: str, output_path: str, voice: str, rate: str = "+0%"):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)

def generate_reddit_audio(text: str, output_path: str, voice: str, rate: str = "+0%"):
    asyncio.run(_gen_audio_async(text, output_path, voice, rate))

def generate_cloned_audio(text: str, output_path: str, ref_wav: str = None):
    if not HAS_QWEN:
        raise Exception("QwenTTS library or utility not found.")
    
    manager = QwenTTSManager.get_instance()
                                                          
    
                                                   
    if not ref_wav:
        clones_dir = resolve_path("assets/clones")
        if os.path.exists(clones_dir):
            files = [f for f in os.listdir(clones_dir) if f.endswith(".wav") and f != "test_voice.wav"]
            if files:
                ref_wav = os.path.join(clones_dir, files[0])
    
    if not ref_wav or not os.path.exists(ref_wav):
        raise Exception("No voice clone reference found. Please create one in the Voice Cloning tab.")
    
    success = manager.generate_audio(text=text, ref_wav_path=ref_wav, output_path=output_path)
    if not success:
        raise Exception("Qwen3-TTS Synthesis failed.")

def load_history():
    try:
        import json
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return list(data.keys())
    except Exception as e:
        print(f"[!] Error loading history: {e}")
    return []

def save_to_history(post_id):
    try:
        import json
        history = load_history()
        if post_id not in history:
            history.append(post_id)
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, "w") as f:
                json.dump(history, f)
            print(f"[+] Saved post {post_id} to history.")
    except Exception as e:
        print(f"[!] Failed to save history: {e}")

from doogclips.utils.reddit_utils import scrape_reddit_post, scrape_subreddit


def estimate_duration(title: str, story: str) -> float:
    words = len(title.split()) + len(story.split())
    return words / 2.5

def split_story_into_parts(story: str, max_part_duration: float = 175.0) -> List[str]:
    words = story.split()
    parts = []
    current_part = []
    current_duration = 0
    for w in words:
        current_part.append(w)
        current_duration += 1 / 2.5
        if current_duration >= max_part_duration:
            if w.endswith((".", "!", "?")):
                parts.append(" ".join(current_part))
                current_part = []
                current_duration = 0
            elif current_duration >= max_part_duration + 5:
                parts.append(" ".join(current_part))
                current_part = []
                current_duration = 0
    if current_part:
        parts.append(" ".join(current_part))
    return parts

def get_subreddit_data(subreddit: str) -> dict:
    if subreddit.lower().startswith("r/"):
        subreddit = subreddit[2:]
    try:
        url = f"https://www.reddit.com/r/{subreddit}/about.json"
        headers = {'User-Agent': 'DoogClips/2.0'}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get('data', {})
            icon = data.get('community_icon') or data.get('icon_img')
            if icon and "&amp;" in icon:
                icon = icon.replace("&amp;", "&")
            return {"icon": icon}
    except: pass
    return {"icon": None}

def create_reddit_overlay(title: str, subreddit: str, icon_url: str = None, target_w: int = 960) -> Image.Image:
    try:
        if icon_url:
            r = requests.get(icon_url, timeout=5)
            avatar = Image.open(BytesIO(r.content)).convert("RGBA")
        else:
            r = requests.get("https://www.redditstatic.com/desktop2x/img/favicon/apple-icon-120x120.png", timeout=5)
            avatar = Image.open(BytesIO(r.content)).convert("RGBA")
        avatar = avatar.resize((64, 64), Image.Resampling.LANCZOS)
    except:
        avatar = Image.new("RGBA", (64, 64), (255, 69, 0, 255))
        d = ImageDraw.Draw(avatar)
        d.ellipse([10, 10, 54, 54], fill="white")

    font_title = _get_font(44, "Verdana Bold")
    font_sub = _get_font(26, "Arial Bold")
    font_time = _get_font(26, "Arial")
    
    words = title.split()
    lines = []
    curr = []
    d_temp = ImageDraw.Draw(Image.new("RGB", (1,1)))
    for w in words:
        curr.append(w)
        text_w = d_temp.textlength(" ".join(curr), font=font_title)
        if text_w > target_w - 60:
            lines.append(" ".join(curr[:-1]))
            curr = [w]
    if curr: lines.append(" ".join(curr))
    line_h = 56
    total_h = 120 + (len(lines) * line_h) + 40
    img = Image.new("RGBA", (target_w, total_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        img.paste(avatar, (30, 30), avatar)
        sub_txt = f"r/{subreddit}" if subreddit else "r/AskReddit"
        sub_w = d_temp.textlength(sub_txt, font=font_sub)
        time_str = f"{random.randint(2, 23)} hr. ago"
        draw.text((110, 35), sub_txt, fill=(28, 28, 28), font=font_sub)
        draw.text((110 + sub_w + 10, 35), f" • {time_str}", fill=(120, 124, 126), font=font_time)
        y = 100
        for line in lines:
            draw.text((30, y), line, fill=(26, 26, 27), font=font_title)
            y += line_h
    except: pass
    return img

def generate_reddit_username():
    prefixes = ["Ad", "Routine", "Special", "Lazy", "Odd", "Simple"]
    suffixes = ["User", "Member", "Soul", "Mind", "Spirit", "Key"]
    return f"u/{random.choice(prefixes)}-{random.choice(suffixes)}-{random.randint(100, 9999)}"

def generate_reddit_timestamp():
    units = ["yr", "mo", "h"]
    u = random.choice(units)
    val = random.randint(1, 24)
    return f"{val}{u}"

def _format_time_ago(ts, now_ts=None):
    try:
        if not ts:
            return ""
        now_ts = now_ts or time.time()
        delta = max(0, int(now_ts - float(ts)))
        if delta >= 31536000:
            return f"{delta // 31536000}y ago"
        if delta >= 2592000:
            return f"{delta // 2592000}mo ago"
        if delta >= 86400:
            return f"{delta // 86400}d ago"
        if delta >= 3600:
            return f"{delta // 3600}h ago"
        if delta >= 60:
            return f"{delta // 60}m ago"
        return "just now"
    except:
        return ""

def _normalize_word(w: str) -> str:
    if not w:
        return ""
    return re.sub(r"[^a-z0-9]+", "", w.lower())

def _find_comment_start_idx(words, comment_text, approx_idx):
    if not words or not comment_text:
        return None
    try:
        hay = [_normalize_word(w.get("word", "")) for w in words]
        target = [_normalize_word(w) for w in comment_text.split()]
        target = [t for t in target if t]
        if not target:
            return min(len(words) - 1, max(0, approx_idx))
        target = target[:6]
        for i in range(0, len(hay) - len(target) + 1):
            if hay[i:i+len(target)] == target:
                return i
        return min(len(words) - 1, max(0, approx_idx))
    except:
        return min(len(words) - 1, max(0, approx_idx)) if words else None

def _reddit_font_path(name: str) -> str:
    fp = resolve_path(os.path.join("assets", "fonts", "redditsans", name))
    if os.path.exists(fp):
        return fp
    return "Verdana"

def render_dropdown_comment_card(
    frame, words, current_time, subreddit, post_username, post_timestamp, story_text, comment_data, comment_start_idx,
    highlight_color=(255, 220, 0), secondary_color=(255, 255, 255),
    frame_w=1080, frame_h=1920, icon_image=None, comment_avatar=None, part_info=None,
    post_score=None, post_comments=None
):
    revealed_count = len([w for w in words if current_time >= w["start"]])
    if revealed_count == 0:
        if part_info:
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            _draw_part_overlay(pil_img, part_info, frame_w, frame_h)
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame

    canvas = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(canvas)
    if part_info:
        _draw_part_overlay(canvas, part_info, frame_w, frame_h)

                                                
    card_bg = (4, 17, 23)
    pill_bg = (28, 36, 46)
    title_color = (243, 246, 247)
    body_color = (178, 186, 190)
    header_color = (236, 238, 240)
    meta_color = (158, 168, 172)

    card_w = 856
    x_off = (frame_w - card_w) // 2
    radius = 18

           
    font_title = _get_font(50, _reddit_font_path("RedditSans-Bold.ttf"))
    font_body = _get_font(30, _reddit_font_path("RedditSans-Regular.ttf"))
    font_header = _get_font(22, _reddit_font_path("RedditSans-SemiBold.ttf"))
    font_user = _get_font(20, _reddit_font_path("RedditSans-Regular.ttf"))
    font_meta = _get_font(20, _reddit_font_path("RedditSans-Regular.ttf"))
    font_pill = _get_font(22, _reddit_font_path("RedditSans-SemiBold.ttf"))
    font_comment_user = _get_font(22, _reddit_font_path("RedditSans-SemiBold.ttf"))
    font_comment_meta = _get_font(20, _reddit_font_path("RedditSans-Regular.ttf"))
    font_comment_body = _get_font(26, _reddit_font_path("RedditSans-Regular.ttf"))

    def draw_text_shadow(x, y, text, font, fill):
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0))
        draw.text((x, y), text, font=font, fill=fill)

    icons = _load_reddit_ui_icons()

                                      
    paragraphs = story_text.split("\n")
    story_lines = []
    word_idx = 0
    for p_idx, para in enumerate(paragraphs):
        if not para.strip():
            story_lines.append(None)
            continue
        is_title = (p_idx == 0 and "Part" not in para[:10])
        active_font = font_title if is_title else font_body
        p_words = para.split()
        curr_line = []
        text_left = x_off + 16
        text_max_w = card_w - (text_left - x_off) - 20
        for pw in p_words:
            capped_idx = min(word_idx, len(words) - 1)
            test_line_str = " ".join([item[1] for item in curr_line] + [pw])
            if draw.textlength(test_line_str, font=active_font) > text_max_w:
                if curr_line:
                    story_lines.append((curr_line, is_title))
                curr_line = [(capped_idx, pw)]
            else:
                curr_line.append((capped_idx, pw))
            if word_idx < len(words):
                word_idx += 1
        if curr_line:
            story_lines.append((curr_line, is_title))

                                                                     
    if story_lines:
        last_title_idx = None
        for i, line in enumerate(story_lines):
            if line is None:
                continue
            if line[1]:
                last_title_idx = i
            elif last_title_idx is not None:
                break
        if last_title_idx is not None and last_title_idx + 1 < len(story_lines):
            if story_lines[last_title_idx + 1] is not None:
                story_lines.insert(last_title_idx + 1, None)

    story_revealed = revealed_count
    if comment_start_idx is not None:
        story_revealed = min(revealed_count, comment_start_idx)

    visible_story_lines = []
    for line_data in story_lines:
        if line_data is None:
            visible_story_lines.append(None)
            continue
        line_items, is_t = line_data
        if line_items and line_items[0][0] < story_revealed:
            visible_story_lines.append(line_data)
        else:
            break

    line_h_title = int(50 * 1.25)
    line_h_body = int(30 * 1.35)
    story_text_h = 0
    for ld in visible_story_lines:
        if ld is None:
            story_text_h += line_h_body // 2
        else:
            story_text_h += line_h_title if ld[1] else line_h_body

    header_h = 102
    footer_pad_top = 18
    pill_h = 64
    footer_pad_bottom = 18
    story_card_h = header_h + story_text_h + footer_pad_top + pill_h + footer_pad_bottom

                       
    comment_body = (comment_data or {}).get("body", "")
    comment_author = (comment_data or {}).get("author", "")
    comment_time = (comment_data or {}).get("timestamp", "")
    comment_edited = (comment_data or {}).get("edited", "")
    show_comment = bool(comment_body) and comment_start_idx is not None and revealed_count >= comment_start_idx

    comment_lines = []
    comment_text_h = 0
    comment_card_h = 0
    if show_comment:
        comment_words = comment_body.split()
        c_word_idx = comment_start_idx
        curr_line = []
        comment_text_left = x_off + 120
        comment_text_max_w = card_w - (comment_text_left - x_off) - 24
        for pw in comment_words:
            capped_idx = min(c_word_idx, len(words) - 1)
            test_line_str = " ".join([item[1] for item in curr_line] + [pw])
            if draw.textlength(test_line_str, font=font_comment_body) > comment_text_max_w:
                if curr_line:
                    comment_lines.append(curr_line)
                curr_line = [(capped_idx, pw)]
            else:
                curr_line.append((capped_idx, pw))
            if c_word_idx < len(words):
                c_word_idx += 1
        if curr_line:
            comment_lines.append(curr_line)

        visible_comment_lines = []
        for line_items in comment_lines:
            if line_items and line_items[0][0] < revealed_count:
                visible_comment_lines.append(line_items)
            else:
                break
        comment_lines = visible_comment_lines
        c_line_h = int(26 * 1.35)
        comment_text_h = sum([c_line_h for _ in comment_lines]) if comment_lines else 0
        comment_header_h = 52
        comment_card_h = comment_header_h + comment_text_h + 18

                                                         
    spacing = 0
    total_h = story_card_h + (comment_card_h + spacing if show_comment else 0)
    y_off = int(frame_h * 0.12)
    if y_off + total_h > frame_h - 40:
        y_off = max(30, frame_h - total_h - 40)
    overlap = 6 if show_comment else 0
    comment_y = y_off + story_card_h - overlap

                           
    draw.rounded_rectangle([x_off, y_off, x_off + card_w, y_off + story_card_h], radius=radius, fill=card_bg)

                                                    
    icon_size = 62
    icon_x = x_off + 3
    icon_y = y_off + 8
    if icon_image:
        ic = icon_image.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (icon_size, icon_size), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.ellipse([0, 0, icon_size, icon_size], fill=255)
        canvas.paste(ic, (icon_x, icon_y), mask)
    elif icons.get("rslash"):
        ic = icons["rslash"].resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        canvas.paste(ic, (icon_x, icon_y), ic)
    else:
        draw.ellipse([icon_x, icon_y, icon_x + icon_size, icon_y + icon_size], fill=(245, 247, 248))
        draw_text_shadow(icon_x + 12, icon_y + 18, "r/", font=_get_font(30, _reddit_font_path("RedditSans-Bold.ttf")), fill=(5, 5, 5))

    sub_txt = f"r/{subreddit}" if subreddit else "r/Reddit"
    header_user = (post_username or generate_reddit_username().replace("u/", "")).replace("u/", "")
    header_time = post_timestamp or f"{random.randint(2, 23)}h ago"

    sub_y = y_off + 18
    sub_x = icon_x + icon_size + 14
    draw_text_shadow(sub_x, sub_y, sub_txt, font=font_header, fill=header_color)
    dot_x = sub_x + int(draw.textlength(sub_txt, font=font_header)) + 10
    draw_text_shadow(dot_x, sub_y, "•", font=font_header, fill=body_color)
    time_x = dot_x + int(draw.textlength("•", font=font_header)) + 10
    draw_text_shadow(time_x, sub_y, header_time, font=font_header, fill=body_color)
    draw_text_shadow(sub_x, sub_y + 28, header_user, font=font_user, fill=meta_color)

               
    dots_x = x_off + card_w - 36
    dots_y = y_off + 26
    for i in range(3):
        dx = dots_x + i * 8
        draw.ellipse([dx, dots_y, dx + 4, dots_y + 4], fill=header_color)

                
    text_y = y_off + header_h
    text_left = x_off + 16
    for line_data in visible_story_lines:
        if line_data is None:
            text_y += line_h_body // 2
            continue
        line_items, is_title = line_data
        text_x = text_left
        active_font = font_title if is_title else font_body
        active_lh = line_h_title if is_title else line_h_body
        active_color = title_color if is_title else body_color
        line_text = " ".join([w for _, w in line_items])
        draw_text_shadow(text_x, text_y, line_text, active_font, active_color)
        text_y += active_lh

                  
    pill_y = y_off + header_h + story_text_h + footer_pad_top
    pill_specs = [
        (x_off + 1, 144),                    
        (x_off + 171, 127),           
        (x_off + 325, 87),         
        (x_off + 439, 162)         
    ]
    for px, pw in pill_specs:
        draw.rounded_rectangle([px, pill_y, px + pw, pill_y + pill_h], radius=22, fill=pill_bg)

                     
    score = str(post_score) if post_score is not None else "0"
    up_x, up_w = pill_specs[0]
    mid_y = pill_y + pill_h // 2
              
    if icons.get("upvote"):
        canvas.paste(icons["upvote"], (up_x + 19, pill_y + 17), icons["upvote"])
                                   
    sw = draw.textlength(score, font=font_pill)
    score_center_x = up_x + 72
    draw_text_shadow(int(score_center_x - sw / 2), pill_y + 24, score, font_pill, title_color)
                
    if icons.get("downvote"):
        canvas.paste(icons["downvote"], (up_x + 98, pill_y + 18), icons["downvote"])

                  
    comments = str(post_comments) if post_comments is not None else "0"
    cx, cw = pill_specs[1]
    if icons.get("comment"):
        canvas.paste(icons["comment"], (cx + 28, pill_y + 18), icons["comment"])
    draw_text_shadow(cx + 74, pill_y + 24, comments, font_pill, title_color)

                
    ax, aw = pill_specs[2]
    if icons.get("award"):
        canvas.paste(icons["award"], (ax + 29, pill_y + 18), icons["award"])

                
    sx, swp = pill_specs[3]
    if icons.get("share"):
        canvas.paste(icons["share"], (sx + 29, pill_y + 20), icons["share"])
    draw_text_shadow(sx + 74, pill_y + 24, "Share", font_pill, title_color)

    if show_comment:
        draw.rounded_rectangle([x_off, comment_y, x_off + card_w, comment_y + comment_card_h], radius=radius, fill=card_bg)
                                                                          
        draw.rectangle([x_off, comment_y, x_off + card_w, comment_y + radius], fill=card_bg)
                
        c_avatar_size = 44
        c_avatar_x = x_off + 18
        c_avatar_y = comment_y + 10
        if comment_avatar:
            try:
                av = comment_avatar.resize((c_avatar_size, c_avatar_size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (c_avatar_size, c_avatar_size), 0)
                mdraw = ImageDraw.Draw(mask)
                mdraw.ellipse([0, 0, c_avatar_size, c_avatar_size], fill=255)
                             
                draw.ellipse([c_avatar_x - 1, c_avatar_y - 1, c_avatar_x + c_avatar_size + 1, c_avatar_y + c_avatar_size + 1], fill=(12, 24, 30))
                canvas.paste(av, (c_avatar_x, c_avatar_y), mask)
            except:
                draw.ellipse([c_avatar_x, c_avatar_y, c_avatar_x + c_avatar_size, c_avatar_y + c_avatar_size], fill=(70, 75, 82))
        else:
            draw.ellipse([c_avatar_x, c_avatar_y, c_avatar_x + c_avatar_size, c_avatar_y + c_avatar_size], fill=(70, 75, 82))

                                                              
        line_x = c_avatar_x + c_avatar_size // 2
        link_y1 = y_off + story_card_h - overlap
        link_y2 = c_avatar_y + c_avatar_size // 2
        if link_y2 > link_y1:
            draw.line([(line_x, link_y1), (line_x, link_y2)], fill=(90, 98, 104), width=2)

                     
        line_x = c_avatar_x + c_avatar_size // 2
        line_y1 = c_avatar_y + c_avatar_size + 6
        line_y2 = comment_y + comment_card_h - 10
        if line_y2 > line_y1:
            draw.line([(line_x, line_y1), (line_x, line_y2)], fill=(90, 98, 104), width=2)

        c_header = comment_author if comment_author else "Commenter"
        c_time = comment_time if comment_time else ""
        time_str = c_time
        if comment_edited:
            time_str = f"{time_str} • Edited {comment_edited}" if time_str else f"Edited {comment_edited}"
        c_text_x = x_off + 120
        draw_text_shadow(c_text_x, comment_y + 10, f"{c_header}  •  {time_str}", font_comment_user, title_color)

        text_start_y = comment_y + 42
        c_line_h = int(26 * 1.35)
        for line_items in comment_lines:
            line_text = " ".join([w for _, w in line_items])
            draw_text_shadow(c_text_x, text_start_y, line_text, font_comment_body, body_color)
            text_start_y += c_line_h

    return cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)
def render_dropdown_card(frame, words, current_time, subreddit, username, timestamp, story_text, highlight_color=(255, 220, 0), frame_w=1080, frame_h=1920, icon_image=None, part_info=None):
    revealed_count = len([w for w in words if current_time >= w["start"] - 0.1])
    if revealed_count == 0:
        if part_info:
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            _draw_part_overlay(pil_img, part_info, frame_w, frame_h)
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame
    

    canvas = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(canvas)
    if part_info:
        _draw_part_overlay(canvas, part_info, frame_w, frame_h)

    story_len = len(story_text)
    if story_len < 250: main_fs = 54
    elif story_len < 600: main_fs = 46
    else: main_fs = 34
    
    font_main = _get_font(main_fs, "Impact")
    font_sub = _get_font(28, "Verdana")
    font_bold = _get_font(32, "Verdana Bold")
    
    margin = 45
    card_w = 940
    x_off = (frame_w - card_w) // 2
    paragraphs = story_text.split("\n")
    all_lines = []
    word_idx = 0
    for para in paragraphs:
        if not para.strip():
            all_lines.append([])
            continue
        p_words = para.split()
        curr_line = []
        for pw in p_words:
            capped_idx = min(word_idx, len(words) - 1)
            test_line_str = " ".join([item[1] for item in curr_line] + [pw])
            if draw.textlength(test_line_str, font=font_main) > card_w - (margin * 2):
                if curr_line: all_lines.append(curr_line)
                curr_line = [(capped_idx, pw)]
            else: curr_line.append((capped_idx, pw))
            if word_idx < len(words): word_idx += 1
        if curr_line: all_lines.append(curr_line)

    header_h = 145
    line_h = int(main_fs * 1.35)
    visible_lines = []
    for line in all_lines:
        if not line: visible_lines.append(line); continue
        if any(idx < revealed_count for idx, txt in line): visible_lines.append(line)
        else: break
            
    total_text_h = sum([line_h if line else line_h // 2 for line in visible_lines])
    card_h = header_h + total_text_h + 30
    y_off = (frame_h - card_h) // 2 - 100
    
    draw.rounded_rectangle([x_off, y_off, x_off + card_w, y_off + card_h], radius=14, fill=(26, 26, 27), outline=(52, 53, 54), width=1)
    if icon_image:
        ic = icon_image.resize((56, 56), Image.Resampling.LANCZOS)
        canvas.paste(ic, (x_off + 25, y_off + 25), ic if ic.mode == "RGBA" else None)
    else: draw.ellipse([x_off + 25, y_off + 25, x_off + 81, y_off + 81], fill=(255, 69, 0))
    
    draw.text((x_off + 95, y_off + 28), f"r/{subreddit}" if subreddit else "r/Reddit", font=font_bold, fill=(215, 218, 220))
    draw.text((x_off + 95, y_off + 68), f"{username} • {timestamp}", font=font_sub, fill=(129, 131, 132))

    current_word_idx = revealed_count - 1
    text_y = y_off + header_h
    for line_items in visible_lines:
        if not line_items: text_y += line_h // 2; continue
        text_x = x_off + margin
        for idx, word_str in line_items:
            if idx >= revealed_count: break
            is_active = (words[idx]["start"] - 0.05 <= current_time <= words[idx]["end"] + 0.05)
            if not is_active and idx == current_word_idx: is_active = True
            color = highlight_color if is_active else (215, 218, 220)
            draw.text((text_x, text_y), word_str + " ", font=font_main, fill=color)
            text_x += draw.textlength(word_str + " ", font=font_main)
        text_y += line_h
    return cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)

def create_reddit_clip(title, story, output_path, subreddit="AskReddit", progress_cb=None, bg_type="Random Preset", bg_custom="", bgm_type="None", bgm_custom="", subtitle_color=(255, 220, 0), font_size=86, max_words=3, voice_id="en-US-ChristopherNeural", custom_audio_path="", style="Regular", secondary_color=(255, 255, 255), font_family="Impact", stroke_width=4, use_glow=False, use_slide=False, enable_emojis=False, show_progress_bar=False, voice_rate="+0%", cancel_cb=None, subreddit_icon_url=None, use_dropdown=False, use_dropdown_comment=False, use_top_comment=True, post_meta=None, comment_data=None, post_id=None, whisper_engine="Base", bgm_volume=0.15, fast_mode=False):
    est_dur = estimate_duration(title, story)
    story_parts = split_story_into_parts(story, 175.0) if est_dur > 180.0 else [story]
    total_parts = len(story_parts)
    generated_files = []
    
    if not use_top_comment:
        comment_data = None

    for part_idx, part_text in enumerate(story_parts):
        current_part_num = part_idx + 1
        part_suffix = f"_part{current_part_num}" if total_parts > 1 else ""
        base, ext = os.path.splitext(output_path)
        part_output_path = f"{base}{part_suffix}{ext}"
        part_info = (current_part_num, total_parts) if total_parts > 1 else None

        if progress_cb:
            p_msg = f"Processing Part {current_part_num}/{total_parts}..." if total_parts > 1 else "Processing Post..."
            progress_cb(p_msg, int((part_idx / total_parts) * 100))

        part_comment = comment_data if (use_top_comment and part_idx == (total_parts - 1)) else None
        res = _generate_single_part(
            title if part_idx == 0 else f"Part {current_part_num}: {title}",
            part_text, part_output_path, subreddit, progress_cb,
            bg_type, bg_custom, bgm_type, bgm_custom,
            subtitle_color, font_size, max_words, voice_id,
            custom_audio_path, style, secondary_color, font_family,
            stroke_width, use_glow, use_slide, enable_emojis,
            show_progress_bar, voice_rate, cancel_cb,
            subreddit_icon_url, use_dropdown, use_dropdown_comment, post_meta, part_comment, part_info, whisper_engine, bgm_volume, fast_mode
        )
        if res: generated_files.append(res)
    if post_id: save_to_history(post_id)
    return generated_files

def _generate_single_part(title, story, output_path, subreddit, progress_cb, bg_type, bg_custom, bgm_type, bgm_custom, subtitle_color, font_size, max_words, voice_id, custom_audio_path, style, secondary_color, font_family, stroke_width, use_glow, use_slide, enable_emojis, show_progress_bar, voice_rate, cancel_cb, subreddit_icon_url, use_dropdown, use_dropdown_comment, post_meta, comment_data, part_info, whisper_engine="Base", bgm_volume=0.15, fast_mode=False):
    out_dir = os.path.dirname(output_path)
    if out_dir: os.makedirs(out_dir, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    if use_dropdown:
        random_user = generate_reddit_username()
        random_time = generate_reddit_timestamp()
        icon_img = None
        if subreddit_icon_url:
            try:
                r = requests.get(subreddit_icon_url, timeout=5)
                icon_img = Image.open(BytesIO(r.content)).convert("RGBA")
            except: pass

    post_author = None
    post_time_ago = None
    post_score = None
    post_comments = None
    if isinstance(post_meta, dict):
        post_author = post_meta.get("author")
        post_time_ago = _format_time_ago(post_meta.get("created_utc"))
        post_score = post_meta.get("score")
        post_comments = post_meta.get("num_comments")

    comment_body = None
    comment_meta = None
    comment_avatar_url = None
    if isinstance(comment_data, dict):
        comment_body = comment_data.get("body", "")
        edited_val = comment_data.get("edited")
        edited_time = _format_time_ago(edited_val) if isinstance(edited_val, (int, float)) else ""
        comment_avatar_url = comment_data.get("avatar")
        comment_meta = {
            "author": comment_data.get("author", ""),
            "timestamp": _format_time_ago(comment_data.get("created_utc")),
            "edited": edited_time,
            "flair": comment_data.get("flair", ""),
            "body": comment_body
        }

    comment_avatar_img = None
    if comment_avatar_url:
        try:
            r = requests.get(comment_avatar_url, timeout=5)
            comment_avatar_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            comment_avatar_img = None
    
    use_custom = (voice_id == "custom" and custom_audio_path and os.path.exists(custom_audio_path))
    if use_custom:
        audio_path = custom_audio_path
        full_text = story 
    else:
        has_title = "Part" not in title or "Part 1" in title
        story_text = f"{title}\n{story}" if has_title else story
        full_text = story_text
        use_comment_audio = bool(use_dropdown_comment and comment_body)
        if use_comment_audio:
            full_text = f"{story_text}\n\n{comment_body}"
        audio_path = os.path.join(TEMP_DIR, f"part_audio_{random.randint(1000,9999)}.mp3")
        if progress_cb: progress_cb(f"Generating Voice...", 10)
        if voice_id == "cloned": 
                                                                             
            ref = custom_audio_path if (custom_audio_path and os.path.exists(custom_audio_path)) else None
            generate_cloned_audio(full_text, audio_path, ref_wav=ref)
        else: generate_reddit_audio(full_text, audio_path, voice_id, rate=voice_rate)
            
    words = transcribe(audio_path, progress_cb=None, engine=whisper_engine, diarize=False)
    comment_start_idx = None
    story_text_for_comment = None
    if use_dropdown_comment and comment_meta and not use_custom:
        story_text_for_comment = f"{title}\n{story}" if ("Part" not in title or "Part 1" in title) else story
        approx_idx = len(story_text_for_comment.split())
        comment_start_idx = _find_comment_start_idx(words, comment_body, approx_idx)
    gameplay_url = get_bg_url(bg_type, bg_custom)
    gp_path = get_gameplay_video([gameplay_url] if gameplay_url else GAMEPLAY_URLS, DOWNLOADS_DIR)
    dur = words[-1]["end"] + 1.2 if words else 10.0
    
    cap = cv2.VideoCapture(gp_path)
    src_fps, src_w, src_h = cap.get(cv2.CAP_PROP_FPS) or 30.0, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target_frames = int(dur * src_fps)
    
    if total_frames > target_frames + 300:
        cap.set(cv2.CAP_PROP_POS_FRAMES, random.randint(0, total_frames - target_frames - 100))
        
    temp_vid = os.path.join(TEMP_DIR, f"temp_{random.randint(1000,9999)}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_vid, fourcc, src_fps, (1080, 1920))
    
    overlay_img = create_reddit_overlay(title, subreddit, icon_url=subreddit_icon_url)
    overlay_np = cv2.cvtColor(np.array(overlay_img), cv2.COLOR_RGBA2BGRA)
    oh, ow = overlay_np.shape[:2]
    oy, ox = (1920 - oh) // 2 - 200, (1080 - ow) // 2
    
    frame_idx = 0
    while frame_idx < target_frames:
        if cancel_cb and cancel_cb():
            cap.release(); out.release(); 
            if os.path.exists(temp_vid): os.remove(temp_vid)
            return None
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret: break
        
        current_time = frame_idx / src_fps
        cw = int(src_h * 1080 / 1920)
        if cw > src_w: cd = frame
        else: x1 = (src_w - cw) // 2; cd = frame[:, x1:x1+cw]
        
        interp = cv2.INTER_LINEAR if fast_mode else cv2.INTER_LANCZOS4
        bg = cv2.resize(cd, (1080, 1920), interpolation=interp)
        if use_dropdown:
            if use_dropdown_comment and comment_meta and not use_custom:
                bg = render_dropdown_comment_card(
                    bg, words, current_time, subreddit, post_author or random_user.replace("u/", ""),
                    post_time_ago or f"{random.randint(2, 23)}h ago",
                    story_text_for_comment or story, comment_meta, comment_start_idx,
                    highlight_color=subtitle_color, secondary_color=secondary_color,
                    frame_w=1080, frame_h=1920, icon_image=icon_img, comment_avatar=comment_avatar_img, part_info=part_info,
                    post_score=post_score, post_comments=post_comments
                )
            else:
                bg = render_dropdown_card(bg, words, current_time, subreddit, random_user, random_time, full_text, subtitle_color, 1080, 1920, icon_image=icon_img, part_info=part_info)
        else:
            if current_time < 4.5:
                roi = bg[oy:oy+oh, ox:ox+ow]
                alpha = overlay_np[:, :, 3] / 255.0
                if fast_mode:
                    alpha_3d = alpha[:, :, np.newaxis]
                    roi = (alpha_3d * overlay_np[:, :, :3] + (1 - alpha_3d) * roi).astype(np.uint8)
                else:
                    for c in range(3): roi[:, :, c] = (alpha * overlay_np[:, :, c] + (1 - alpha) * roi[:, :, c]).astype(np.uint8)
                bg[oy:oy+oh, ox:ox+ow] = roi
            bg = render_subtitle_frame(bg, words, current_time, 1080, 1920, subtitle_color, secondary_color, font_size, max_words, style, font_family, stroke_width, use_glow, use_slide, enable_emojis=enable_emojis, show_progress_bar=show_progress_bar, duration=dur, part_info=part_info)
        out.write(bg)
        frame_idx += 1
        
    cap.release(); out.release()
                                                   
    cmd = ["ffmpeg", "-y", "-i", temp_vid, "-i", audio_path]
    bgm_path = get_bgm_path(bgm_type, bgm_custom)
    if bgm_path and os.path.exists(bgm_path):
        cmd += ["-stream_loop", "-1", "-i", bgm_path, "-filter_complex", f"[2:a]volume={bgm_volume}[bgm];[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]", "-map", "0:v:0", "-map", "[aout]"]
    else: cmd += ["-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0"]
    cmd += ["-c:v", "copy", "-shortest", output_path]
    subprocess.run(cmd, capture_output=True)
                                 
    if os.path.exists(temp_vid): os.remove(temp_vid)
    if not use_custom and os.path.exists(audio_path): os.remove(audio_path)
    return output_path

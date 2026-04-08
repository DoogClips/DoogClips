import urllib.request
import json
import re

                                                         
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def format_title_for_display(title: str) -> str:
    """Formats a raw Reddit title for YouTube display: case, currency, and length."""
                       
    title = title.strip()
    
                                                          
    def format_money(match):
        val = match.group(0)
                            
        if len(val) >= 4 and val not in ["2022", "2023", "2024", "2025"]:
            try:
                num = int(val.replace("$", "").replace(",", ""))
                return f"${num:,}"
            except: return val
        return val
    
                                                                                 
    if "$" not in title and "£" not in title and "€" not in title:
        title = re.sub(r'\b\d{4,}\b', format_money, title)
    
                                                 
    title = title.replace(" usd ", " USD ").replace(" eur ", " EUR ").replace(" gbp ", " GBP ")
    
    return title[:100]

def _extract_flair_text(author_flair_text, author_flair_richtext):
    if author_flair_text:
        return author_flair_text
    if isinstance(author_flair_richtext, list):
        parts = []
        for item in author_flair_richtext:
            if isinstance(item, dict) and item.get("e") == "text":
                parts.append(item.get("t", ""))
        if parts:
            return "".join(parts).strip()
    return None

def _fetch_user_avatar(username: str) -> str:
    if not username:
        return ""
    try:
        url = f"https://www.reddit.com/user/{username}/about.json"
        headers = {'User-Agent': UA}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            u = data.get("data", {})
            icon = u.get("snoovatar_img") or u.get("icon_img") or ""
            if icon and "&amp;" in icon:
                icon = icon.replace("&amp;", "&")
            return icon or ""
    except:
        return ""

def _fetch_subreddit_icon(subreddit: str) -> str:
    if not subreddit:
        return ""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/about.json"
        headers = {'User-Agent': UA}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            d = data.get("data", {})
            icon = d.get("community_icon") or d.get("icon_img") or ""
            if icon and "&amp;" in icon:
                icon = icon.replace("&amp;", "&")
            return icon or ""
    except:
        return ""

def scrape_reddit_post(url: str) -> dict:
    """Zero-dependency scraper using built-in urllib with browser-like headers."""
    if url.endswith("/"): url = url[:-1]
    if ".json" not in url:
        if "?" in url:
            base, q = url.split("?", 1)
            url = f"{base}.json?{q}"
        else:
            url += ".json"
    if "sort=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sort=top"
    
    headers = {'User-Agent': UA}
    req = urllib.request.Request(url, headers=headers)
    
                                                                    
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode())
        post = data[0]['data']['children'][0]['data']
        sub_icon = _fetch_subreddit_icon(post.get('subreddit', ''))
        
        top_comment = None
        try:
            comments = data[1]['data']['children'] if len(data) > 1 else []
            for c in comments:
                if c.get("kind") != "t1":
                    continue
                cdata = c.get("data", {})
                body = cdata.get("body", "")
                if not body or body in ("[deleted]", "[removed]"):
                    continue
                top_comment = {
                    "author": cdata.get("author", ""),
                    "body": body,
                    "created_utc": cdata.get("created_utc"),
                    "edited": cdata.get("edited"),
                    "flair": _extract_flair_text(cdata.get("author_flair_text"), cdata.get("author_flair_richtext")),
                    "avatar": _fetch_user_avatar(cdata.get("author", ""))
                }
                break
        except:
            top_comment = None
        
        return {
            "title": post.get('title', ''),
            "story": post.get('selftext', ''),
            "subreddit": post.get('subreddit', ''),
            "id": post.get('id', ''),
            "author": post.get("author", ""),
            "created_utc": post.get("created_utc"),
            "comment": top_comment,
            "sub_icon": sub_icon,
            "score": post.get("score"),
            "num_comments": post.get("num_comments")
        }

def scrape_subreddit(subreddit: str, limit: int = 10, time_filter: str = "day") -> list:
    """Zero-dependency subreddit scraper."""
    s = subreddit.strip().lower()
    if "reddit.com/r/" in s:
        s = s.split("reddit.com/r/")[1].split("/")[0]
    elif s.startswith("r/"):
        s = s[2:]
    
    url = f"https://www.reddit.com/r/{s}/top.json?t={time_filter}&limit={limit*2}"
    headers = {'User-Agent': UA}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            posts = []
            for child in data.get('data', {}).get('children', []):
                p = child['data']
                if p.get('is_self') and p.get('selftext'):
                    posts.append({
                        "id": p.get('id'),
                        "url": f"https://www.reddit.com{p.get('permalink')}",
                        "title": p.get('title'),
                        "story": p.get('selftext'),
                        "subreddit": p.get('subreddit')
                    })
            return posts
    except: return []

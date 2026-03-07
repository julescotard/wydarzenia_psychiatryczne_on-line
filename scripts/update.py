#!/usr/bin/env python3
import json, re, sys, os
from datetime import datetime, date, timedelta
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

UA = "Mozilla/5.0 (compatible; wydarzenia_psychiatryczne/1.1)"
TIMEOUT = 30

# Date patterns (PL numeric) + dateutil fallback
DATE_PATTERNS = [
    # 13–14.03.2026 / 13-14.03.2026
    re.compile(r"(?P<d1>\d{1,2})\s*[–\-]\s*(?P<d2>\d{1,2})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<y>20\d{2})"),
    # 13.03.2026
    re.compile(r"(?P<d>\d{1,2})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<y>20\d{2})"),
    # 2026-03-13
    re.compile(r"(?P<y>20\d{2})[-/\.](?P<m>\d{1,2})[-/\.](?P<d>\d{1,2})"),
]

def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def normalize_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)

def is_allowed(url, allowed_domains):
    host = urlparse(url).netloc.lower().replace("www.","")
    return any(host == d or host.endswith("." + d) for d in allowed_domains)

def discover_links(listing_url, html, allowed_domains):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#"):
            continue
        absu = urljoin(listing_url, href)
        if not absu.lower().startswith(("http://","https://")):
            continue
        if not is_allowed(absu, allowed_domains):
            continue
        low = absu.lower()
        # heuristic: keep likely event pages
        if any(k in low for k in ["202","psychiatr","kongres","konferenc","warsztat","szkolen","webinar","cns","forum","spotkan","kurs"]):
            links.add(absu.split("#")[0])
    return links

def detect_any(text, keywords):
    t = text.lower()
    return any(k in t for k in keywords)

def extract_dates(text):
    # Prefer explicit patterns
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        gd = m.groupdict()
        if "d1" in gd:
            d1 = int(gd["d1"]); d2 = int(gd["d2"]); mth = int(gd["m"]); y = int(gd["y"])
            start = date(y, mth, d1)
            end = date(y, mth, d2) + timedelta(days=1)
            return start, end
        d = int(gd["d"]); mth = int(gd["m"]); y = int(gd["y"])
        start = date(y, mth, d)
        return start, start + timedelta(days=1)

    # Fallback: try dateutil near a year token (20xx)
    years = re.findall(r"(20\d{2})", text)
    for y in years[:3]:
        idx = text.find(y)
        window = text[max(0, idx-60): idx+60]
        try:
            dt = dtparser.parse(window, dayfirst=True, fuzzy=True)
            if 2000 <= dt.year <= 2100:
                start = dt.date()
                return start, start + timedelta(days=1)
        except Exception:
            continue
    return None, None

def extract_location(text):
    # Simple heuristics
    m = re.search(r"(Miejsce|Lokalizacja|Venue|Location)\s*[:\-]\s*([^\.]{3,160})", text, re.IGNORECASE)
    if m:
        return m.group(2).strip()
    for c in ["Warszawa","Kraków","Poznań","Wrocław","Gdańsk","Katowice","Łódź","Lublin","Zamość","Wisła","Gniezno","Sopot","Gdynia","Szczecin","Bydgoszcz","Toruń"]:
        if c.lower() in text.lower():
            return c
    return ""

def title_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return "Wydarzenie psychiatryczne"

def clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*[\|\-–]\s*.*$", "", t).strip()
    return t[:140]

def build_event(url, html, cfg):
    text = normalize_text(html)
    start, end = extract_dates(text)
    if start is None:
        return None

    cancelled = detect_any(text, cfg["keywords_cancelled"])
    if cancelled:
        return {"url": url, "status": "CANCELLED", "title": clean_title(title_from_html(html)), "start": start.isoformat(), "end": end.isoformat(), "location": extract_location(text)}

    online_hit = detect_any(text, cfg["keywords_online"])
    offline_hit = detect_any(text, cfg["keywords_offline"])
    loc = extract_location(text)

    mode = cfg.get("mode","online")
    if mode == "online":
        if not online_hit:
            return None
    else: # offline
        # Include if offline indicated OR location present. Exclude purely-online pages with no location and no offline hint.
        if not (offline_hit or loc):
            return None

    return {"url": url, "status": "CONFIRMED", "title": clean_title(title_from_html(html)), "start": start.isoformat(), "end": end.isoformat(), "location": loc}

def ics_escape(s):
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")

def fold(line, limit=75):
    if len(line) <= limit:
        return line
    out = []
    while len(line) > limit:
        out.append(line[:limit])
        line = " " + line[limit:]
    out.append(line)
    return "\r\n".join(out)

def vtimezone_block(tzid="Europe/Warsaw"):
    return [
        "BEGIN:VTIMEZONE",
        f"TZID:{tzid}",
        f"X-LIC-LOCATION:{tzid}",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

def write_ics(events, out_path, calname, tzid):
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//wydarzenia_psychiatryczne//PL online/offline//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-TIMEZONE:{tzid}",
        f"X-WR-CALNAME:{calname}",
    ]
    lines += vtimezone_block(tzid)

    for ev in events:
        uid = re.sub(r"[^a-zA-Z0-9]", "", ev["url"])[-28:] + "@wydarzenia-psychiatryczne"
        start = date.fromisoformat(ev["start"])
        end = date.fromisoformat(ev["end"])
        desc = (ev.get("location","") + "\n\nLink: " + ev["url"]).strip()
        lines += [
            "BEGIN:VEVENT",
            fold("UID:" + uid),
            "DTSTAMP:" + now_utc,
            fold("SUMMARY:" + ics_escape(ev["title"])),
            "DTSTART;VALUE=DATE:" + start.strftime("%Y%m%d"),
            "DTEND;VALUE=DATE:" + end.strftime("%Y%m%d"),
            fold("LOCATION:" + ics_escape(ev.get("location",""))),
            fold("DESCRIPTION:" + ics_escape(desc)),
            fold("URL:" + ev["url"]),
            "STATUS:" + ev.get("status","CONFIRMED"),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    content = "\r\n".join(lines) + "\r\n"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

def write_events_html(events, out_path, title):
    rows = []
    for ev in events:
        rows.append(f"<li><b>{ev['start']}</b> — <a href='{ev['url']}'>{ev['title']}</a>" + (f" <span style='color:#666'>({ev.get('location','')})</span>" if ev.get("location") else "") + "</li>")
    body = "\n".join(rows) if rows else "<p>Brak znalezionych wydarzeń (spełniających filtry) w aktualnym horyzoncie.</p>"
    html = f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; margin:24px; line-height:1.5; }}
li {{ margin: 8px 0; }}
a {{ word-break: break-word; }}
</style>
</head>
<body>
<h1>{title}</h1>
<ul>
{body}
</ul>
</body>
</html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

def load_prev(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def diff_events(prev, cur):
    prev_by_url = {e["url"]: e for e in prev}
    cur_by_url = {e["url"]: e for e in cur}
    added = [cur_by_url[u] for u in (cur_by_url.keys() - prev_by_url.keys())]
    removed = [prev_by_url[u] for u in (prev_by_url.keys() - cur_by_url.keys())]
    changed = []
    for u in (cur_by_url.keys() & prev_by_url.keys()):
        a = prev_by_url[u]; b = cur_by_url[u]
        keys = ["title","start","end","location","status"]
        if any(a.get(k) != b.get(k) for k in keys):
            changed.append({"before": a, "after": b})
    return added, changed, removed

def main():
    cfg = load_config()
    prev_path = os.path.join("data","events.json")
    prev = load_prev(prev_path)

    urls = set(cfg.get("seed_event_urls", []))

    # Best-effort discovery
    for page in cfg.get("discovery_pages", []):
        try:
            html = get(page)
            urls |= discover_links(page, html, cfg["allowed_domains"])
        except Exception:
            continue

    urls = sorted([u for u in urls if is_allowed(u, cfg["allowed_domains"])])

    gathered = []
    for u in urls:
        try:
            html = get(u)
            ev = build_event(u, html, cfg)
            if not ev:
                continue
            # remove cancelled items from published list (user requirement)
            if ev.get("status") == "CANCELLED":
                continue
            gathered.append(ev)
        except Exception:
            continue

    uniq = {e["url"]: e for e in gathered}
    cur = list(uniq.values())

    # Apply rolling horizon to keep calendar manageable
    today = date.today()
    past = int(cfg.get("horizon_days_past", 30))
    future = int(cfg.get("horizon_days_future", 730))
    min_d = today - timedelta(days=past)
    max_d = today + timedelta(days=future)

    cur = [e for e in cur if (min_d <= date.fromisoformat(e["start"]) <= max_d)]
    cur.sort(key=lambda e: (e["start"], e["title"].lower()))

    added, changed, removed = diff_events(prev, cur)

    os.makedirs("data", exist_ok=True)
    with open(prev_path, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)

    mode = cfg.get("mode","online")
    calname = "Wydarzenia psychiatryczne (online/VOD)" if mode=="online" else "Wydarzenia psychiatryczne (offline)"
    write_ics(cur, os.path.join("docs", cfg["calendar_filename"]), calname, cfg["timezone"])
    write_events_html(cur, os.path.join("docs","events.html"), calname)

    stamp = datetime.now().strftime("%Y-%m-%d")
    md = ["## Zmiany wykryte: " + stamp, ""]
    if not (added or changed or removed):
        md.append("Brak zmian w wydarzeniach.")
    else:
        if added:
            md += ["### Nowe"] + [f"- {e['title']} ({e['start']}) – {e['url']}" for e in added] + [""]
        if changed:
            md += ["### Zmienione"]
            for ch in changed:
                b = ch["before"]; a = ch["after"]
                md.append(f"- {a['title']} – {a['url']}")
                md.append(f"  - było: {b['start']} → {b['end']} | {b.get('location','')}")
                md.append(f"  - jest: {a['start']} → {a['end']} | {a.get('location','')}")
            md.append("")
        if removed:
            md += ["### Usunięte (np. odwołane / wypadły z horyzontu)"] + [f"- {e['title']} – {e['url']}" for e in removed] + [""]

    with open(os.path.join("data","changes.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md).strip() + "\n")

    if added or changed or removed:
        sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()

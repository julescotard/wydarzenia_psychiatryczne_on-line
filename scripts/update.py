#!/usr/bin/env python3
import json, re, sys, os
from datetime import datetime, date, timedelta
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

UA = "Mozilla/5.0 (compatible; wydarzenia_psychiatryczne/FINAL)"
TIMEOUT = 35

PL_MONTHS = {
    "stycznia": 1, "styczen": 1, "styczeń": 1, "styczniu": 1,
    "lutego": 2, "luty": 2, "lutym": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecien": 4, "kwiecień": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpien": 8, "sierpień": 8,
    "września": 9, "wrzesnia": 9, "wrzesien": 9, "wrzesień": 9,
    "października": 10, "pazdziernika": 10, "październik": 10, "pazdziernik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzien": 12, "grudzień": 12,
}

DATE_PATTERNS = [
    re.compile(r"(?P<d1>\d{1,2})\s*[–\-]\s*(?P<d2>\d{1,2})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<y>20\d{2})"),
    re.compile(r"(?P<d>\d{1,2})\s*\.\s*(?P<m>\d{1,2})\s*\.\s*(?P<y>20\d{2})"),
    re.compile(r"(?P<y>20\d{2})[-/\.](?P<m>\d{1,2})[-/\.](?P<d>\d{1,2})"),
    re.compile(r"(?P<d1>\d{1,2})\s*[–\-]\s*(?P<d2>\d{1,2})\s*(?P<mon>[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)\s*(?P<y>20\d{2})", re.IGNORECASE),
    re.compile(r"(?P<d>\d{1,2})\s*(?P<mon>[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)\s*(?P<y>20\d{2})", re.IGNORECASE),
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

def score_psychiatry(text, cfg):
    t = text.lower()
    score = 0
    for k in cfg["include_terms_strong"]:
        if k in t:
            score += 3
    for k in cfg["include_terms_weak"]:
        if k in t:
            score += 1
    for k in cfg["exclude_terms"]:
        if k in t:
            score -= 3
    if "psychiatr" in t:
        score += 2
    return score

def has_online_access(text, cfg):
    t = text.lower()
    if any(k in t for k in cfg["online_strong"]):
        return True
    if any(k in t for k in cfg["online_weak"]):
        if any(x in t for x in ["udział", "uczestnict", "transmis", "na żywo", "live", "zapis", "nagran", "vod", "replay", "platform", "zdalnie"]):
            return True
    return False

def has_offline_access(text, cfg):
    t = text.lower()
    if any(k in t for k in cfg["offline_terms"]):
        return True
    if any(c.lower() in t for c in cfg["cities"]):
        return True
    return False

def detect_cancelled(text, cfg):
    t = text.lower()
    return any(k in t for k in cfg["cancelled_terms"])

def extract_location(text, cfg):
    m = re.search(r"(Miejsce|Lokalizacja|Venue|Location)\s*[:\-]\s*([^\.]{3,180})", text, re.IGNORECASE)
    if m:
        return m.group(2).strip()
    for c in cfg["cities"]:
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
    return "Wydarzenie"

def clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*[\|\-–]\s*.*$", "", t).strip()
    return t[:170]

def extract_dates(text):
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        gd = {k:v for k,v in m.groupdict().items() if v is not None}
        if "mon" in gd:
            mon = gd["mon"].lower()
            mon = mon.replace("ą","a").replace("ę","e").replace("ł","l").replace("ń","n").replace("ó","o").replace("ś","s").replace("ź","z").replace("ż","z")
            mon_num = PL_MONTHS.get(mon)
            if not mon_num:
                continue
            y = int(gd["y"])
            if "d1" in gd:
                d1 = int(gd["d1"]); d2 = int(gd["d2"])
                start = date(y, mon_num, d1)
                end = date(y, mon_num, d2) + timedelta(days=1)
                return start, end
            d = int(gd["d"])
            start = date(y, mon_num, d)
            return start, start + timedelta(days=1)

        if "d1" in gd:
            d1 = int(gd["d1"]); d2 = int(gd["d2"]); mth = int(gd["m"]); y = int(gd["y"])
            start = date(y, mth, d1)
            end = date(y, mth, d2) + timedelta(days=1)
            return start, end
        d = int(gd["d"]); mth = int(gd["m"]); y = int(gd["y"])
        start = date(y, mth, d)
        return start, start + timedelta(days=1)

    years = re.findall(r"(20\d{2})", text)
    for y in years[:5]:
        idx = text.find(y)
        window = text[max(0, idx-120): idx+120]
        try:
            dt = dtparser.parse(window, dayfirst=True, fuzzy=True)
            if 2000 <= dt.year <= 2100:
                start = dt.date()
                return start, start + timedelta(days=1)
        except Exception:
            continue
    return None, None

def discover_links(listing_url, html, cfg):
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#"):
            continue
        absu = urljoin(listing_url, href)
        if not absu.lower().startswith(("http://","https://")):
            continue
        if not is_allowed(absu, cfg["allowed_domains"]):
            continue
        anchor = a.get_text(" ", strip=True)[:250]
        candidate_text = (anchor + " " + absu).lower()
        score = score_psychiatry(candidate_text, cfg)
        if score < cfg["min_score_link"]:
            continue
        low = absu.lower()
        if any(x in low for x in ["cookies", "polityka", "regulamin", "kontakt", "login"]):
            continue
        links.add(absu.split("#")[0])
    return links

def build_event(url, html, cfg, is_seed=False):
    text = normalize_text(html)
    title = clean_title(title_from_html(html))
    combined = title + " " + text
    score = score_psychiatry(combined, cfg)
    if (not is_seed) and score < cfg["min_score_event"]:
        return None
    start, end = extract_dates(combined)
    if start is None:
        return None
    if detect_cancelled(combined, cfg):
        return {"url": url, "status":"CANCELLED", "title": title, "start": start.isoformat(), "end": end.isoformat(), "location": extract_location(combined, cfg), "score": score}

    loc = extract_location(combined, cfg)
    if cfg.get("mode") == "online":
        if not has_online_access(combined, cfg):
            return None
    else:
        if not has_offline_access(combined, cfg) and not loc:
            return None

    return {"url": url, "status":"CONFIRMED", "title": title, "start": start.isoformat(), "end": end.isoformat(), "location": loc, "score": score}

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
        "PRODID:-//wydarzenia_psychiatryczne//PL//FINAL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-TIMEZONE:{tzid}",
        f"X-WR-CALNAME:{calname}",
    ]
    lines += vtimezone_block(tzid)
    for ev in events:
        uid = re.sub(r"[^a-zA-Z0-9]", "", ev["url"])[-32:] + "@wydarzenia-psychiatryczne"
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
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")

def write_events_html(events, out_path, title):
    rows = []
    for ev in events:
        loc = ev.get("location","")
        loc_html = f" <span style='color:#666'>({loc})</span>" if loc else ""
        score = ev.get("score", 0)
        rows.append(f"<li><b>{ev['start']}</b> — <a href='{ev['url']}'>{ev['title']}</a>{loc_html} <span style='color:#999'>(score {score})</span></li>")
    body = "\n".join(rows) if rows else "<p>Brak znalezionych wydarzeń w aktualnym horyzoncie.</p>"
    html = f"<!doctype html><html lang='pl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{title}</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;margin:24px;line-height:1.5}}li{{margin:8px 0}}a{{word-break:break-word}}</style></head><body><h1>{title}</h1><ul>{body}</ul></body></html>"
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

    seed_urls = set(cfg.get("seed_event_urls", []))
    urls = set(seed_urls)
    for page in cfg.get("discovery_pages", []):
        try:
            html = get(page)
            urls |= discover_links(page, html, cfg)
        except Exception:
            continue

    urls = sorted([u for u in urls if is_allowed(u, cfg["allowed_domains"])])

    gathered = []
    for u in urls:
        try:
            html = get(u)
            ev = build_event(u, html, cfg, is_seed=(u in seed_urls))
            if not ev or ev.get("status") == "CANCELLED":
                continue
            gathered.append(ev)
        except Exception:
            continue

    cur = list({e["url"]: e for e in gathered}.values())

    today = date.today()
    min_d = today - timedelta(days=int(cfg.get("horizon_days_past", 60)))
    max_d = today + timedelta(days=int(cfg.get("horizon_days_future", 900)))
    cur = [e for e in cur if (min_d <= date.fromisoformat(e["start"]) <= max_d)]
    cur.sort(key=lambda e: (e["start"], e["title"].lower()))

    added, changed, removed = diff_events(prev, cur)

    with open(prev_path, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)

    calname = "Wydarzenia psychiatryczne (online/VOD)" if cfg.get("mode") == "online" else "Wydarzenia psychiatryczne (offline)"
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
            md += ["### Usunięte"] + [f"- {e['title']} – {e['url']}" for e in removed] + [""]
    with open(os.path.join("data","changes.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md).strip() + "\n")

    if added or changed or removed:
        sys.exit(2)
    sys.exit(0)

if __name__ == "__main__":
    main()

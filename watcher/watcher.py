#!/usr/bin/env python3
"""Tail Postfix's mail.log -> sent.log / rejected.log / deferred.log + Discord webhook.
Stdlib only. Correlates by queue ID: client IP, subject, sender, then delivery result."""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request

MAIL_LOG = os.environ.get("MAIL_LOG", "/logs/mail.log")
OUT = os.environ.get("OUT_DIR", "/logs")
HOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
NOTIFY = {x.strip() for x in os.environ.get("DISCORD_NOTIFY", "rejected,bounced,expired,deferred").split(",") if x.strip()}
NAME = os.environ.get("RELAY_HOSTNAME", "mail-relay")
STATE_FILE = os.path.join(OUT, ".watcher_offset")

LINE = re.compile(r"^(?P<ts>\w{3}\s+\d+ \d\d:\d\d:\d\d) \S+ postfix/(?P<prog>[\w/-]+)\[\d+\]: (?P<msg>.*)$")
CLIENT = re.compile(r"^(?P<q>\w+): client=(?P<c>\S+)")
SUBJ = re.compile(r"^(?P<q>\w+): warning: header Subject: (?P<s>.*?) from \S+\[[^\]]*\];")
FROM = re.compile(r"^(?P<q>\w+): from=<(?P<f>[^>]*)>, size=(?P<sz>\d+)")
DELIV = re.compile(r"^(?P<q>\w+): to=<(?P<t>[^>]*)>,(?: orig_to=<[^>]*>,)? relay=(?P<r>[^,]+), .*?status=(?P<st>\w+) \((?P<d>.*)\)$")
EXPIRED = re.compile(r"^(?P<q>\w+): from=<(?P<f>[^>]*)>, status=expired")
REJECT = re.compile(r"^NOQUEUE: reject: \w+ from (?P<c>\S+): (?P<d>.*?); from=<(?P<f>[^>]*)> to=<(?P<t>[^>]*)>")
REMOVED = re.compile(r"^(?P<q>\w+): removed$")

COLORS = {"sent": 0x2ECC71, "deferred": 0xF1C40F, "bounced": 0xE74C3C, "rejected": 0xE74C3C, "expired": 0xE67E22}
FILES = {"sent": "sent.log", "deferred": "deferred.log", "bounced": "rejected.log", "rejected": "rejected.log", "expired": "rejected.log"}

msgs = {}          # queue id -> {client, subject, from, size}
deferred_seen = set()


def stamp(ts):
    try:
        t = dt.datetime.strptime(f"{dt.date.today().year} {ts}", "%Y %b %d %H:%M:%S")
        return t.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def write(kind, ts, m, to, detail, qid, relay=""):
    line = " | ".join([
        stamp(ts), kind.upper(), f"{m.get('from') or '<>'} -> {to or '?'}",
        f"subject: {m.get('subject', '')}", f"client: {m.get('client', '')}",
        f"qid: {qid}", f"relay: {relay}" if relay else "", detail,
    ])
    with open(os.path.join(OUT, FILES[kind]), "a", encoding="utf-8") as fh:
        fh.write(line.replace(" |  |", " |") + "\n")
    print(line, flush=True)
    if kind in NOTIFY:
        discord(kind, m, to, detail, qid)


def discord(kind, m, to, detail, qid):
    if not HOOK:
        return
    fields = [("From", m.get("from") or "<>"), ("To", to or "?"), ("Client", m.get("client") or "?"),
              ("Subject", m.get("subject") or "-"), ("Detail", detail or "-"), ("Queue ID", qid or "-")]
    body = {"username": NAME, "embeds": [{
        "title": f"Mail {kind}",
        "color": COLORS.get(kind, 0x95A5A6),
        "fields": [{"name": k, "value": str(v)[:1024], "inline": k in ("From", "To", "Client")} for k, v in fields],
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }]}
    req = urllib.request.Request(HOOK, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "busse-mail-relay/1.0"})
    for _ in range(3):
        try:
            urllib.request.urlopen(req, timeout=10).close()
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = float(json.loads(e.read()).get("retry_after", 2))
                except Exception:
                    wait = 2
                time.sleep(wait)
                continue
            print(f"discord error {e.code}: {e.read()[:200]!r}", flush=True)
            return
        except Exception as e:  # network hiccup
            print(f"discord error: {e}", flush=True)
            time.sleep(2)


def handle(raw):
    lm = LINE.match(raw.rstrip("\n"))
    if not lm:
        return
    ts, msg = lm["ts"], lm["msg"]
    if r := CLIENT.match(msg):
        msgs.setdefault(r["q"], {})["client"] = r["c"]
    elif r := SUBJ.match(msg):
        msgs.setdefault(r["q"], {})["subject"] = r["s"]
    elif r := FROM.match(msg):
        m = msgs.setdefault(r["q"], {})
        m["from"], m["size"] = r["f"], r["sz"]
    elif r := DELIV.match(msg):
        st, q = r["st"], r["q"]
        if st == "deferred":
            if q in deferred_seen:
                return  # only report first deferral per message
            deferred_seen.add(q)
        if st in FILES:
            write(st, ts, msgs.get(q, {}), r["t"], r["d"], q, r["r"])
    elif r := EXPIRED.match(msg):
        write("expired", ts, msgs.get(r["q"], {"from": r["f"]}), "", "gave up after queue lifetime", r["q"])
    elif r := REJECT.match(msg):
        write("rejected", ts, {"from": r["f"], "client": r["c"]}, r["t"], r["d"], "NOQUEUE")
    elif r := REMOVED.match(msg):
        msgs.pop(r["q"], None)
        deferred_seen.discard(r["q"])
    if len(msgs) > 5000:  # safety valve
        msgs.clear()


def load_state():
    try:
        with open(STATE_FILE) as fh:
            s = json.load(fh)
        return s.get("ino"), s.get("off", 0)
    except Exception:
        return None, 0


def save_state(ino, off):
    try:
        with open(STATE_FILE, "w") as fh:
            json.dump({"ino": ino, "off": off}, fh)
    except OSError:
        pass


def follow():
    saved_ino, saved_off = load_state()
    fh, ino, last_save = None, None, 0.0
    while True:
        if fh is None:
            try:
                fh = open(MAIL_LOG, "r", encoding="utf-8", errors="replace")
            except FileNotFoundError:
                time.sleep(2)
                continue
            ino = os.fstat(fh.fileno()).st_ino
            size = os.fstat(fh.fileno()).st_size
            if ino == saved_ino and saved_off <= size:
                fh.seek(saved_off)  # resume where we left off after a restart
            print(f"watching {MAIL_LOG} (discord {'on' if HOOK else 'off'}, notify={sorted(NOTIFY)})", flush=True)
        line = fh.readline()
        if line:
            handle(line)
            continue
        if time.time() - last_save > 5:
            save_state(ino, fh.tell())
            last_save = time.time()
        try:
            st = os.stat(MAIL_LOG)
            if st.st_ino != ino or st.st_size < fh.tell():  # rotated or truncated
                fh.close()
                fh, saved_ino, saved_off = None, None, 0
                continue
        except FileNotFoundError:
            pass
        time.sleep(1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    follow()

import feedparser, smtplib, yaml, os
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic

# Load config
with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
cutoff = datetime.utcnow() - timedelta(days=4)  # Mon/Thu window

def fetch_rss(url, name):
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:5]:
        pub = datetime(*e.published_parsed[:6]) if hasattr(e, 'published_parsed') and e.published_parsed else datetime.utcnow()
        if pub >= cutoff:
            items.append(f"[{name}] {e.title}: {getattr(e, 'summary', '')[:300]}")
    return items

def fetch_reddit(person):
    import urllib.request, json
    q = urllib.request.quote(person)
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit=5&t=week"
    req = urllib.request.Request(url, headers={"User-Agent": "newsletter-bot/1.0"})
    data = json.loads(urllib.request.urlopen(req).read())
    return [f"[Reddit/{person}] {p['data']['title']}" for p in data["data"]["children"]]

# Gather all content
all_items = []
for person in cfg["people"]:
    for rss_url in person.get("rss", []):
        all_items += fetch_rss(rss_url, person["name"])
    if person.get("reddit"):
        all_items += fetch_reddit(person["name"])

# Summarize with Claude
content_block = "\n".join(all_items) or "No new content found."
resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1200,
    messages=[{"role": "user", "content": f"""
You are an AI research assistant. Summarize the latest content from these AI thought leaders.
Group by person. Be concise. Focus on key ideas and insights.

RAW CONTENT:
{content_block}

Format as a clean email digest with an intro line and bullet points per person.
"""}]
)
summary = resp.content[0].text

# Send email
msg = MIMEMultipart("alternative")
msg["Subject"] = f"AI Superstar Digest — {datetime.utcnow().strftime('%b %d')}"
msg["From"] = os.environ["GMAIL_USER"]
msg["To"] = cfg["to_email"]
msg.attach(MIMEText(summary, "plain"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
    s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    s.sendmail(os.environ["GMAIL_USER"], cfg["to_email"], msg.as_string())

print("Digest sent!")

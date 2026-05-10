"""
Reddit Daily Digest
-------------------
Fetches all posts from the past 24 hours from Reddit RSS feeds
then emails a formatted digest.

Setup:
  pip install requests

Schedule via Task Scheduler to run at startup.
"""

import requests
import smtplib
import datetime
import re
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ─────────────────────────────────────────────
#  YOUR SETTINGS — edit these
# ─────────────────────────────────────────────

SUBREDDITS = [
    "sysadmin",
    "AzureVirtualDesktop",
    "windows365",
    "Intune",
    "homelab",
    "AI_Agents",
    "ClaudeAI",
    "MicrosoftEntra",
    "Office365",
    "artificial",
    "NewTubers",
    "youtubeCreators",
    "MSP",
    "ITCareerQuestions",
]

EMAIL_FROM    = "youremailhere"
EMAIL_TO      = ["youremailhere"]
EMAIL_SUBJECT = "Daily Reddit Digest — {date}"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "youremailhere"
SMTP_PASSWORD = "xxxxxxx"

# ─────────────────────────────────────────────


def fetch_rss_posts(subreddit: str, hours: int = 24) -> list:
    """Fetch all posts from the past N hours from a subreddit RSS feed."""
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit=100"
    headers = {"User-Agent": "RedditDigest/1.0 (personal script)"}
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()

    root = ET.fromstring(res.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

    posts = []
    for entry in root.findall("atom:entry", ns):
        title   = entry.find("atom:title", ns)
        link    = entry.find("atom:link", ns)
        updated = entry.find("atom:updated", ns)
        content = entry.find("atom:content", ns)

        if title is None or link is None:
            continue

        post_dt = None
        if updated is not None and updated.text:
            try:
                post_dt = datetime.datetime.fromisoformat(updated.text.replace("Z", "+00:00"))
            except Exception:
                pass

        if post_dt and post_dt < cutoff:
            continue

        body = ""
        if content is not None and content.text:
            body = re.sub(r'<[^>]+>', ' ', content.text)
            body = re.sub(r'\s+', ' ', body).strip()
            body = re.sub(r'submitted by.*', '', body, flags=re.IGNORECASE).strip()
            body = body[:300]

        posts.append({
            "title":   title.text.strip(),
            "url":     link.get("href", ""),
            "updated": updated.text.strip() if updated is not None else "",
            "body":    body,
        })

    return posts


def format_post_date(updated: str) -> str:
    """Format an ISO timestamp into a readable date/time string."""
    if not updated:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(updated.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y %H:%M UTC")
    except Exception:
        return updated


def build_html(results: list, date_str: str) -> str:
    """Build a clean HTML email body."""
    sections = ""
    for r in results:
        sub        = r["subreddit"]
        posts      = r["posts"]
        post_count = len(posts)

        if not posts:
            post_rows = '<div style="font-size:13px;color:#aaa;padding:8px 0;">No new posts in the last 24 hours.</div>'
        else:
            post_rows = ""
            for p in posts:
                post_date = format_post_date(p.get("updated", ""))

                body_html = ""
                if p.get("body"):
                    preview = p["body"][:200]
                    if len(p["body"]) > 200:
                        preview += "…"
                    body_html = f'<div style="font-size:12px;color:#888;margin-top:3px;line-height:1.5;">{preview}</div>'

                post_rows += f"""
                <div style="padding:8px 0;border-bottom:1px solid #f0f0f0;">
                  <div style="display:flex;justify-content:space-between;
                              align-items:baseline;gap:10px;">
                    <a href="{p['url']}" style="font-size:13px;color:#1a1a1a;
                                                 text-decoration:none;line-height:1.4;
                                                 font-weight:500;" target="_blank">
                      {p['title']}
                    </a>
                    <span style="font-size:11px;color:#bbb;white-space:nowrap;
                                 flex-shrink:0;">{post_date}</span>
                  </div>
                  {body_html}
                </div>"""

        sections += f"""
        <div style="margin-bottom:32px;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;
                      margin-bottom:10px;">
            <div style="font-size:13px;font-weight:600;color:#888;
                        text-transform:uppercase;letter-spacing:0.05em;">r/{sub}</div>
            <div style="font-size:12px;color:#bbb;">{post_count} post{'s' if post_count != 1 else ''} in last 24h</div>
          </div>
          <div style="margin-bottom:8px;">
            {post_rows}
          </div>
          <div style="margin-top:6px;">
            <a href="https://reddit.com/r/{sub}/new"
               style="font-size:12px;color:#0066cc;text-decoration:none;">
              View r/{sub}/new &rarr;
            </a>
          </div>
        </div>
        <hr style="border:none;border-top:1px solid #eee;margin:0 0 28px;">
        """

    return f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                        sans-serif;max-width:640px;margin:0 auto;padding:32px 24px;
                        background:#fff;">
      <div style="margin-bottom:28px;">
        <div style="font-size:22px;font-weight:600;color:#1a1a1a;margin-bottom:4px;">
          Reddit Digest
        </div>
        <div style="font-size:13px;color:#888;">{date_str}</div>
      </div>
      {sections}
      <div style="font-size:12px;color:#aaa;margin-top:16px;">
        Reddit RSS &middot; Last 24 hours
      </div>
    </body></html>
    """


def send_email(html_body: str, date_str: str):
    """Send the digest email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT.format(date=date_str)
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(EMAIL_TO)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())


def main():
    date_str = datetime.date.today().strftime("%A, %d %B %Y")
    print(f"\nReddit Digest — {date_str}")
    print("=" * 40)

    results = []

    for sub in SUBREDDITS:
        try:
            print(f"  Fetching r/{sub}...")
            posts = fetch_rss_posts(sub, hours=24)
            print(f"  Found {len(posts)} posts in last 24h")
            results.append({"subreddit": sub, "posts": posts})
        except Exception as e:
            print(f"  Error on r/{sub}: {e}")
            results.append({"subreddit": sub, "posts": []})

    print("\nSending email...")
    html = build_html(results, date_str)
    send_email(html, date_str)
    print("Done! Digest sent to", ", ".join(EMAIL_TO))


if __name__ == "__main__":
    main()

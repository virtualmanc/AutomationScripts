"""
Reddit Daily Digest
-------------------
Fetches posts from Reddit RSS feeds, summarises them with Claude,
then emails a formatted digest with post titles, body previews,
timestamps and a summary.

Setup:
  pip install anthropic requests

Configure the settings below, then run once to test.
Schedule via Task Scheduler to run at startup.
"""

import anthropic
import requests
import smtplib
import datetime
import time
import re
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ─────────────────────────────────────────────
#  YOUR SETTINGS — edit these
# ─────────────────────────────────────────────

ANTHROPIC_API_KEY = "sk-ant-your-key-here"

SUBREDDITS = [
    "sysadmin",
    "AzureVirtualDesktop",
    "windows365",
    "Intune",
    "homelab",
]

EMAIL_FROM    = "yourneil@gmail.com"
EMAIL_TO      = "wvdadmin@virtualmanc.co.uk"
EMAIL_SUBJECT = "Daily Reddit Digest — {date}"
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "yourneil@gmail.com"
SMTP_PASSWORD = "abcdefghijklmnop"   # 16-char Gmail App Password, no spaces

DELAY_BETWEEN_SUBREDDITS = 15

# ─────────────────────────────────────────────


def fetch_rss_posts(subreddit: str) -> list:
    """Fetch posts from a subreddit RSS feed."""
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss"
    headers = {"User-Agent": "RedditDigest/1.0 (personal script)"}
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()

    root = ET.fromstring(res.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    posts = []
    for entry in root.findall("atom:entry", ns):
        title   = entry.find("atom:title", ns)
        link    = entry.find("atom:link", ns)
        updated = entry.find("atom:updated", ns)
        content = entry.find("atom:content", ns)

        # Strip HTML tags from content to get plain text preview
        body = ""
        if content is not None and content.text:
            body = re.sub(r'<[^>]+>', ' ', content.text)
            body = re.sub(r'\s+', ' ', body).strip()
            body = re.sub(r'submitted by.*', '', body, flags=re.IGNORECASE).strip()
            body = body[:300]

        if title is not None and link is not None:
            posts.append({
                "title":   title.text.strip(),
                "url":     link.get("href", ""),
                "updated": updated.text.strip() if updated is not None else "",
                "body":    body,
            })

    return posts[:25]


def format_post_date(updated: str) -> str:
    """Format an ISO timestamp into a readable date/time string."""
    if not updated:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(updated.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y %H:%M UTC")
    except Exception:
        return updated


def summarise_posts(client: anthropic.Anthropic, subreddit: str, posts: list) -> str:
    """Ask Claude to summarise the fetched posts."""
    if not posts:
        return "No posts found."

    posts_text = "\n".join(
        f"{i+1}. \"{p['title']}\""
        + (f"\n   {p['body']}" if p.get("body") else "")
        for i, p in enumerate(posts)
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Here are the latest posts from r/{subreddit} on Reddit:\n\n"
                    f"{posts_text}\n\n"
                    f"Write a concise 4-6 sentence summary of the key themes and topics "
                    f"being discussed. Be specific and mention actual post titles where relevant. "
                    f"Plain paragraphs only, no bullet points or headers."
                ),
            }
        ],
    )

    text_blocks = [b.text for b in response.content if b.type == "text"]
    return "\n".join(text_blocks).strip() or "No summary available."


def build_html(results: list, date_str: str) -> str:
    """Build a clean HTML email body."""
    sections = ""
    for r in results:
        sub     = r["subreddit"]
        summary = r["summary"]
        posts   = r["posts"]

        post_rows = ""
        for p in posts[:15]:
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
          <div style="font-size:13px;font-weight:600;color:#888;
                      text-transform:uppercase;letter-spacing:0.05em;
                      margin-bottom:10px;">r/{sub}</div>

          <div style="margin-bottom:16px;">
            {post_rows}
          </div>

          <div style="font-size:14px;line-height:1.75;color:#444;
                      padding:12px;background:#f9f9f9;border-radius:6px;">
            {summary.replace(chr(10), '<br>')}
          </div>

          <div style="margin-top:8px;">
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
        Generated by Claude &middot; Reddit RSS
      </div>
    </body></html>
    """


def send_email(html_body: str, date_str: str):
    """Send the digest email."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = EMAIL_SUBJECT.format(date=date_str)
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())


def main():
    date_str = datetime.date.today().strftime("%A, %d %B %Y")
    print(f"\nReddit Digest — {date_str}")
    print("=" * 40)

    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    results = []

    for i, sub in enumerate(SUBREDDITS):
        try:
            print(f"  Fetching r/{sub}...")
            posts = fetch_rss_posts(sub)
            print(f"  Found {len(posts)} posts — summarising...")
            summary = summarise_posts(client, sub, posts)
            results.append({"subreddit": sub, "summary": summary, "posts": posts})
        except Exception as e:
            print(f"  Error on r/{sub}: {e}")
            results.append({"subreddit": sub, "summary": f"Failed to load: {e}", "posts": []})

        if i < len(SUBREDDITS) - 1:
            print(f"  Waiting {DELAY_BETWEEN_SUBREDDITS}s...")
            time.sleep(DELAY_BETWEEN_SUBREDDITS)

    print("\nSending email...")
    html = build_html(results, date_str)
    send_email(html, date_str)
    print("Done! Digest sent to", EMAIL_TO)


if __name__ == "__main__":
    main()

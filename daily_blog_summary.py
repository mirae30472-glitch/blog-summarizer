import os
import feedparser
import requests
import smtplib
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import anthropic

# ────────────────────────────────────────────
# 설정
# ────────────────────────────────────────────
RSS_FEEDS = [
    {"name": "ranto28 블로그", "url": "https://rss.blog.naver.com/ranto28"},
    {"name": "서정덕TV 블로그", "url": "https://seojdmorgan.tistory.com/rss"},
]

EMAIL_FROM    = os.environ["EMAIL_FROM"]      # GitHub Secret
EMAIL_TO      = os.environ["EMAIL_TO"]        # GitHub Secret
EMAIL_PASS    = os.environ["EMAIL_PASS"]      # Gmail 앱 비밀번호
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]  # GitHub Secret

KST = timezone(timedelta(hours=9))
HOURS_LIMIT = 24  # 최근 몇 시간 이내 글만 가져올지


# ────────────────────────────────────────────
# 1. RSS에서 최근 글 목록 가져오기
# ────────────────────────────────────────────
def get_recent_entries(feed_url: str) -> list[dict]:
    feed = feedparser.parse(feed_url)
    now = datetime.now(KST)
    results = []

    for entry in feed.entries:
        # 날짜 파싱
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(KST)
        else:
            continue  # 날짜 없으면 스킵

        if (now - pub).total_seconds() <= HOURS_LIMIT * 3600:
            results.append({
                "title": entry.title,
                "link":  entry.link,
                "date":  pub.strftime("%Y-%m-%d %H:%M"),
            })

    return results


# ────────────────────────────────────────────
# 2. 본문 스크래핑
# ────────────────────────────────────────────
def scrape_content(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 네이버 블로그
        for selector in ["div.se-main-container", "div#postViewArea"]:
            tag = soup.select_one(selector)
            if tag:
                return tag.get_text(separator="\n", strip=True)[:3000]

        # 티스토리
        for selector in ["div.entry-content", "div.article-view", "div#content"]:
            tag = soup.select_one(selector)
            if tag:
                return tag.get_text(separator="\n", strip=True)[:3000]

        # 그 외 — body 전체 텍스트
        return soup.get_text(separator="\n", strip=True)[:3000]

    except Exception as e:
        return f"[본문 가져오기 실패: {e}]"


# ────────────────────────────────────────────
# 3. Claude API로 3줄 요약
# ────────────────────────────────────────────
def summarize(title: str, content: str) -> str:
    if content.startswith("[본문 가져오기 실패"):
        return content

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"제목: {title}\n\n본문:\n{content}\n\n위 블로그 글을 핵심 내용 3줄로 요약해줘. 한국어로."

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ────────────────────────────────────────────
# 4. 이메일 발송
# ────────────────────────────────────────────
def send_email(body: str):
    today = datetime.now(KST).strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 오늘의 블로그 요약 - {today}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    print("✅ 이메일 발송 완료")


# ────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────
def main():
    all_items = []  # (date_str, blog_name, title, summary, link)

    for feed in RSS_FEEDS:
        entries = get_recent_entries(feed["url"])
        for e in entries:
            print(f"  스크래핑 중: {e['title']}")
            content = scrape_content(e["link"])
            summary = summarize(e["title"], content)
            all_items.append((e["date"], feed["name"], e["title"], summary, e["link"]))

    # 최신순 정렬
    all_items.sort(key=lambda x: x[0], reverse=True)

    if not all_items:
        body = "오늘 새 글 없음"
    else:
        lines = []
        for date, blog, title, summary, link in all_items:
            lines.append(f"[{blog}]")
            lines.append(f"✅ {title}")
            lines.append(f"📅 {date}")
            lines.append(f"📝 {summary}")
            lines.append(f"🔗 {link}")
            lines.append("")
        body = "\n".join(lines)

    print(body)
    send_email(body)


if __name__ == "__main__":
    main()

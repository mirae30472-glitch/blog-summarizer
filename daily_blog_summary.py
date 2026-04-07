cat > daily_blog_summary.py << 'ENDOFFILE'
import feedparser
import smtplib
import os
import re
import pytz
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dateutil import parser as date_parser

try:
    import google.generativeai as genai
except ImportError:
    genai = None

RSS_FEEDS = [
    {"name": "ranto28", "url": "https://rss.blog.naver.com/ranto28"}
]
TO_EMAIL = "mirae30472@gmail.com"
FROM_EMAIL = os.environ.get("SENDER_EMAIL")
EMAIL_PASSWORD = os.environ.get("SENDER_APP_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

KST = pytz.timezone('Asia/Seoul')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_html(text):
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def get_summary(text):
    if not GEMINI_API_KEY:
        return "- API 키가 설정되지 않아 요약을 생성할 수 없습니다."
    if not genai:
        return "- google-generativeai 라이브러리가 설치되지 않았습니다."
    if not text or len(text.strip()) < 10:
        return "- 요약할 블로그 내용이 충분하지 않습니다."
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""당신은 아주 친절하고 상냥한 블로그 요약 전문가입니다.
다음 블로그 글의 내용을 읽고, 아래의 규칙에 맞춰서 요약해 주세요.
1. 말투: 부드럽고 친절한 말투를 사용해 주세요.
2. 이모지: 문장 곳곳에 내용과 어울리는 이모지를 넣어주세요.
3. 내용 구성:
   - 🌟 오늘의 한 줄 평
   - 📝 주요 내용 세부 요약
   - 💡 나의 생각/팁

블로그 내용:
{text[:5000]}"""
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        else:
            return "- AI가 내용을 생성하지 못했습니다."
    except Exception as e:
        return f"- 요약 생성 중 오류 발생: {e}"

def fetch_rss_with_requests(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        print(f"  RSS 응답 코드: {response.status_code}, 크기: {len(response.content)} bytes")
        return feedparser.parse(response.content)
    except Exception as e:
        print(f"  RSS 요청 실패: {e}, feedparser 직접 시도...")
        return feedparser.parse(url)

def fetch_recent_posts():
    now_kst = datetime.now(KST)
    time_limit = now_kst - timedelta(hours=48)
    recent_posts = []
    error_logs = []
    for feed_info in RSS_FEEDS:
        print(f"\n{feed_info['name']} RSS 가져오는 중... ({feed_info['url']})")
        parsed_feed = fetch_rss_with_requests(feed_info["url"])
        if parsed_feed.bozo:
            error_logs.append(f"{feed_info['name']} RSS 파싱 경고: {parsed_feed.bozo_exception}")
        entry_count = len(parsed_feed.entries)
        print(f"  총 {entry_count}개 글 발견")
        if entry_count == 0:
            error_logs.append(f"{feed_info['name']}: RSS에서 글을 못 가져왔습니다.")
            continue
        blog_title = parsed_feed.feed.title if 'title' in parsed_feed.feed else feed_info["name"]
        for i, entry in enumerate(parsed_feed.entries):
            try:
                if 'published' in entry:
                    entry_date = date_parser.parse(entry.published)
                elif 'updated' in entry:
                    entry_date = date_parser.parse(entry.updated)
                else:
                    continue
                if entry_date.tzinfo is None:
                    entry_date = KST.localize(entry_date)
                else:
                    entry_date = entry_date.astimezone(KST)
                if i < 3:
                    print(f"  [{i}] {entry.title[:30]}... -> {entry_date.strftime('%Y-%m-%d %H:%M')} KST")
                if entry_date >= time_limit:
                    content = entry.description if 'description' in entry else entry.title
                    if 'content' in entry and len(entry.content) > 0:
                        content = entry.content[0].value
                    cleaned_content = clean_html(content)
                    recent_posts.append({
                        "blog_name": blog_title,
                        "title": entry.title,
                        "date": entry_date,
                        "link": entry.link,
                        "content": cleaned_content
                    })
            except Exception as e:
                error_logs.append(f"{feed_info['name']} 글 파싱 오류: {e}")
    recent_posts.sort(key=lambda x: x["date"], reverse=True)
    return recent_posts, error_logs

def send_email(subject, body):
    if not FROM_EMAIL or not EMAIL_PASSWORD:
        print("이메일 발신 정보 없음. 터미널에만 출력합니다.")
        print(f"제목: {subject}\n\n{body}")
        return
    msg = MIMEMultipart()
    msg['From'] = FROM_EMAIL
    msg['To'] = TO_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(FROM_EMAIL, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("이메일 발송 성공!")
    except Exception as e:
        print(f"이메일 발송 실패: {e}")

def main():
    print(f"블로그 새 글 확인 시작... ({datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')})")
    recent_posts, error_logs = fetch_recent_posts()
    today_str = datetime.now(KST).strftime('%Y년 %m월 %d일')
    subject = f"📰 오늘의 블로그 요약 - {today_str}"
    if not recent_posts:
        if error_logs:
            body = "⚠️ 블로그 요약 중 문제 발생:\n\n" + "\n".join(error_logs)
            body += "\n\n---\n48시간 이내 새 글도 발견되지 않았습니다."
        else:
            body = "오늘 새 글 없음 (48시간 이내 새 글 없음)"
    else:
        body_lines = []
        for post in recent_posts:
            summary = get_summary(post["content"])
            date_str = post["date"].strftime('%Y-%m-%d %H:%M')
            post_text = f"[{post['blog_name']}]\n"
            post_text += f"✅ 제목: {post['title']}\n"
            post_text += f"📅 작성일: {date_str}\n"
            post_text += f"📝 핵심 내용 요약\n{summary}\n"
            post_text += f"🔗 링크: {post['link']}"
            body_lines.append(post_text)
        body = "\n\n".join(body_lines)
    print(f"\n=== 요약 결과 ===\n{subject}\n\n{body}")
    send_email(subject, body)

if __name__ == "__main__":
    main()
ENDOFFILE

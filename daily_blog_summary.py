import feedparser
from datetime import datetime, timedelta
import pytz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai
import os
import re
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Configuration
RSS_FEEDS = [
    {"name": "ranto28", "url": "https://rss.blog.naver.com/ranto28"},
    {"name": "seojdmorgan", "url": "https://seojdmorgan.tistory.com/rss"}
]
TO_EMAIL = "mirae30472@gmail.com"
FROM_EMAIL = os.environ.get("SENDER_EMAIL") 
EMAIL_PASSWORD = os.environ.get("SENDER_APP_PASSWORD") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Set timezone
KST = pytz.timezone('Asia/Seoul')

def get_summary(text):
    if not GEMINI_API_KEY:
        return "- API 키가 설정되지 않아 요약을 생성할 수 없습니다."
        
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""# 이 부분을 찾아서 아래처럼 내용을 늘려보세요!
prompt = f"""
당신은 아주 친절하고 상냥한 블로그 요약 전문가입니다. 
다음 블로그 글의 내용을 읽고, 아래의 규칙에 맞춰서 요약해 주세요.

1. 말투: "~했어요", "~랍니다", "추천드려요!"와 같이 부드럽고 친절한 말투를 사용해 주세요.
2. 이모지: 문장 곳곳에 내용과 어울리는 귀여운 이모지(😊, ✨, 📍 등)를 풍부하게 넣어주세요.
3. 내용 구성:
   - 🌟 **오늘의 한 줄 평**: 이 글을 한 줄로 멋지게 정의해 주세요.
   - 📝 **주요 내용 세부 요약**: 중요한 내용을 3~5가지 포인트로 아주 상세하게 설명해 주세요.
   - 💡 **나의 생각/팁**: 이 글을 읽고 독자가 얻을 수 있는 유익한 팁이나 느낀 점을 적어주세요.

블로그 내용:
{blog_content}
"""

내용:
{text[:5000]}"""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"- 요약 생성 실패: {e}"

def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text(separator=' ', strip=True)

def fetch_recent_posts():
    now_kst = datetime.now(KST)
    time_limit = now_kst - timedelta(hours=24)
    recent_posts = []

    for feed_info in RSS_FEEDS:
        parsed_feed = feedparser.parse(feed_info["url"])
        blog_title = parsed_feed.feed.title if 'title' in parsed_feed.feed else feed_info["name"]
        
        for entry in parsed_feed.entries:
            try:
                # Parse date
                if 'published' in entry:
                    entry_date = date_parser.parse(entry.published)
                elif 'updated' in entry:
                    entry_date = date_parser.parse(entry.updated)
                else:
                    continue
                
                # Make entry date timezone aware KST
                if entry_date.tzinfo is None:
                    entry_date = KST.localize(entry_date)
                else:
                    entry_date = entry_date.astimezone(KST)
                
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
                print(f"Error parsing entry: {e}")
                
    # Sort by date descending
    recent_posts.sort(key=lambda x: x["date"], reverse=True)
    return recent_posts

def send_email(subject, body):
    if not FROM_EMAIL or not EMAIL_PASSWORD:
        print("이메일 발신 정보가 설정되지 않아 터미널에만 출력합니다.\n" + "="*50)
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
    print(f"블로그 새 글 확인 시작... ({datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')})")
    recent_posts = fetch_recent_posts()
    
    today_str = datetime.now(KST).strftime('%Y년 %m월 %d일')
    subject = f"📰 오늘의 블로그 요약 - {today_str}"
    
    if not recent_posts:
        body = "오늘 새 글 없음"
    else:
        body_lines = []
        for post in recent_posts:
            summary = get_summary(post["content"])
            date_str = post["date"].strftime('%Y-%m-%d %H:%M')
            
            post_text = f"[{post['blog_name']}]\n"
            post_text += f"✅ 제목: {post['title']}\n"
            post_text += f"📅 작성일: {date_str}\n"
            post_text += f"📝 핵심 내용 3줄 요약\n{summary}\n"
            post_text += f"🔗 링크: {post['link']}"
            
            body_lines.append(post_text)
            
        body = "\n\n".join(body_lines)
        
    print(f"=== 요약 결과 ===\n{subject}\n\n{body}")
    send_email(subject, body)

if __name__ == "__main__":
    main()


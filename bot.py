import os
import re
import html
import json
import requests
import feedparser
from urllib.parse import urlparse

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

FEED_URLS_ENV = os.environ.get('FEED_URLS', '')
FEED_URLS = [url.strip() for url in FEED_URLS_ENV.split(',') if url.strip()]

SEEN_FILE = 'seen_posts.json'

def clean_text(raw_html):
    """تنظيف النصوص من وسوم HTML والمسافات الزائدة"""
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', '', raw_html)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_source_name(feed, feed_url):
    """استخراج اسم المصدر من الـ Feed أو من اسم النطاق"""
    feed_title = feed.feed.get('title', '').strip()
    if feed_title and "RSS" not in feed_title:
        return feed_title
    domain = urlparse(feed_url).netloc.replace('www.', '')
    return domain.capitalize()

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_seen(seen):
    with open(SEEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        res_data = res.json()
        if not res_data.get("ok"):
            print(f"فشل الإرسال: {res_data.get('description')}")
        else:
            print("تم الإرسال بنجاح إلى تيليجرام.")
    except Exception as e:
        print(f"خطأ أثناء الاتصال بتيليجرام: {e}")

def format_message(source_name, title, summary, link):
    """تنسيق الرسالة بصيغة HTML أنيقة ومستقرة"""
    safe_source = html.escape(source_name)
    safe_title = html.escape(title)
    
    body = f"📢 <b>خبر / منشور جديد</b>\n"
    body += f"🏷️ <b>المصدر:</b> {safe_source}\n"
    body += "━━━━━━━━━━━━━━━━━━\n\n"
    body += f"📌 <b>{safe_title}</b>\n\n"
    
    if summary and summary != title:
        trimmed_summary = summary[:280] + ("..." if len(summary) > 280 else "")
        body += f"{html.escape(trimmed_summary)}\n\n"
        
    body += f"🔗 <a href='{link}'>اضغط هنا لقراءة الخبر كاملاً</a>"
    return body

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID or not FEED_URLS:
        print("المتغيرات البيئية غير مكتملة (TELEGRAM_TOKEN, CHAT_ID, FEED_URLS).")
        return

    seen_posts = load_seen()
    new_seen = seen_posts.copy()

    for feed_url in FEED_URLS:
        print(f"جاري الفحص: {feed_url}")
        feed = feedparser.parse(feed_url)
        source_name = extract_source_name(feed, feed_url)

        for entry in reversed(feed.entries):
            post_id = entry.get('id') or entry.get('link') or entry.get('title')
            if not post_id or post_id in seen_posts:
                continue

            raw_title = clean_text(entry.get('title', 'بدون عنوان'))
            raw_summary = clean_text(entry.get('summary', ''))
            link = entry.get('link', '').strip()

            if not link:
                continue

            message = format_message(source_name, raw_title, raw_summary, link)
            send_telegram(message)
            new_seen.append(post_id)

    if len(new_seen) > 200:
        new_seen = new_seen[-200:]

    save_seen(new_seen)

if __name__ == '__main__':
    main()

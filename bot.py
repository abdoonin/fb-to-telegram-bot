import os
import feedparser
import requests
import json

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# قراءة روابط الـ RSS من إعدادات GitHub Secrets (متغير FEED_URLS)
FEED_URLS_ENV = os.environ.get('FEED_URLS', '')
FEED_URLS = [url.strip() for url in FEED_URLS_ENV.split(',') if url.strip()]

SEEN_FILE = 'seen_posts.json'

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r') as f:
            return json.load(f)
    return []

def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID or not FEED_URLS:
        print("الرجاء التأكد من ضبط الأسرار والمتغيرات البيئية بشكل صحيح.")
        return

    seen_posts = load_seen()
    new_seen = seen_posts.copy()
    
    for feed_url in FEED_URLS:
        print(f"جاري فحص الرابط: {feed_url}")
        feed = feedparser.parse(feed_url)
        
        for entry in reversed(feed.entries):
            post_id = entry.get('id', entry.link)
            if post_id not in seen_posts:
                title = entry.get('title', 'منشور جديد')
                link = entry.link
                message = f"📢 *خبر / منشور جديد*\n\n{title}\n\n🔗 [رابط المصدر]({link})"
                
                send_telegram(message)
                new_seen.append(post_id)

    # الاحتفاظ بآخر 150 منشوراً فقط لمنع تضخم ملف التخزين المؤقت
    if len(new_seen) > 150:
        new_seen = new_seen[-150:]

    save_seen(new_seen)

if __name__ == '__main__':
    main()

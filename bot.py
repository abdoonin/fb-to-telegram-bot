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
    """تنظيف النصوص من وسوم HTML والمسافات المفرطة مع الاحتفاظ بالمعنى"""
    if not raw_html:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    # تنظيف الأسطر الفارغة الزائدة
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join([line for line in lines if line]).strip()

def extract_image(entry):
    """استخراج رابط الصورة من مختلف وسوم الـ RSS الممكنة"""
    # 1. فحص media_content
    if 'media_content' in entry and entry.media_content:
        for media in entry.media_content:
            if 'url' in media:
                return media['url']

    # 2. فحص enclosures
    if 'enclosures' in entry and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/') or enc.get('href', '').endswith(('.jpg', '.jpeg', '.png', '.webp')):
                return enc.get('href')

    # 3. فحص media_thumbnail
    if 'media_thumbnail' in entry and entry.media_thumbnail:
        return entry.media_thumbnail[0].get('url')

    # 4. استخراج الصورة من كود HTML في الوصف أو المحتوى
    content_html = ""
    if 'content' in entry and entry.content:
        content_html = entry.content[0].get('value', '')
    elif 'summary' in entry:
        content_html = entry.get('summary', '')

    if content_html:
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html, re.IGNORECASE)
        if img_match:
            return img_match.group(1)

    return None

def extract_source_name(feed, feed_url):
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

def send_telegram(message, image_url=None):
    """إرسال الخبر بصورة إن وجدت، أو كنص فقط إذا لم تتوفر صورة"""
    if image_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": message,
            "parse_mode": "HTML"
        }
    else:
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
            # إذا فشل إرسال الصورة بسبب صيغة أو رابط تالف، نعيد إرسال المنشور كنص فقط
            if image_url:
                send_telegram(message, image_url=None)
            else:
                print(f"فشل الإرسال: {res_data.get('description')}")
        else:
            print("تم النشر بنجاح.")
    except Exception as e:
        print(f"خطأ في الاتصال بتيليجرام: {e}")

def format_message(source_name, title, full_text, link, has_image=False):
    safe_source = html.escape(source_name)
    safe_title = html.escape(title)

    header = f"📢 <b>خبر / منشور جديد</b>\n🏷️ <b>المصدر:</b> {safe_source}\n━━━━━━━━━━━━━━━━━━\n\n📌 <b>{safe_title}</b>\n\n"
    footer = f"\n\n🔗 <a href='{link}'>اضغط هنا لقراءة الخبر كاملاً</a>"

    # حساب الحد المتاح للنص (تيليجرام يسمح بـ 1024 حرف للـ Caption مع الصورة، و 4096 للرسالة النصية العادية)
    limit = 1024 if has_image else 4096
    overhead = len(header) + len(footer)
    available_chars = limit - overhead - 10

    body_text = ""
    if full_text and full_text != title:
        if len(full_text) > available_chars:
            trimmed = full_text[:available_chars].rsplit(' ', 1)[0] + "..."
            body_text = html.escape(trimmed)
        else:
            body_text = html.escape(full_text)

    return f"{header}{body_text}{footer}"

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID or not FEED_URLS:
        print("المتغيرات البيئية غير مكتملة.")
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

            # استخراج النص الأطول المتاح (محتوى المقال أو الوصف)
            raw_content = ""
            if 'content' in entry and entry.content:
                raw_content = entry.content[0].get('value', '')
            elif 'description' in entry:
                raw_content = entry.get('description', '')
            elif 'summary' in entry:
                raw_content = entry.get('summary', '')

            full_text = clean_text(raw_content)
            link = entry.get('link', '').strip()
            image_url = extract_image(entry)

            if not link:
                continue

            message = format_message(source_name, raw_title, full_text, link, has_image=bool(image_url))
            send_telegram(message, image_url=image_url)
            new_seen.append(post_id)

    if len(new_seen) > 200:
        new_seen = new_seen[-200:]

    save_seen(new_seen)

if __name__ == '__main__':
    main()

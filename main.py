import requests
import threading
import time
import logging
import os
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ─── Logging Setup ───────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

# ─── Telegram Bot Token from environment ────
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ─── Proxy Sources ───────────────────────────
PROXY_SOURCES = [
    ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt", "socks5"),
    ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt", "socks4"),
    ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt", "http"),
    ("https://www.proxy-list.download/api/v1/get?type=http", "http"),
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&timeout=20000", "auto"),
    ("https://www.proxyscan.io/api/proxy?type=http", "http"),
]

TEST_URL = "https://www.google.com"

# ─── Flask Server to stay alive ─────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!", 200

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# Start Flask in a separate thread
threading.Thread(target=run_flask).start()

# ─── Fetch Proxies ───────────────────────────
def fetch_proxies():
    all_proxies = []
    logging.info("[+] Fetching fresh proxies...")
    for url, ptype in PROXY_SOURCES:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                text = response.text.strip()
                # Handle proxyscan.io JSON
                if url.startswith("https://www.proxyscan.io/api/proxy"):
                    try:
                        json_data = response.json()
                        proxies = [
                            (f"{item['Ip']}:{item['Port']}", ptype)
                            for item in json_data if "Ip" in item and "Port" in item
                        ]
                    except Exception:
                        proxies = []
                # Handle proxyscrape API format
                elif url.startswith("https://api.proxyscrape.com/v4/"):
                    raw_list = text.splitlines()
                    proxies = []
                    for line in raw_list:
                        if "://" in line:
                            proto, addr = line.split("://", 1)
                            proxies.append((addr.strip(), proto.strip()))
                else:
                    raw_list = text.splitlines()
                    proxies = [(proxy.strip(), ptype) for proxy in raw_list if proxy.strip()]
                all_proxies.extend(proxies)
                logging.info(f"[✔] Fetched {len(proxies)} proxies from {url}")
            else:
                logging.warning(f"[✖] Failed to fetch from {url}")
        except Exception as e:
            logging.warning(f"[✖] Error fetching from {url}: {e}")
    logging.info(f"[✔] Total proxies fetched: {len(all_proxies)}")
    return all_proxies

# ─── Test Proxy ──────────────────────────────
def test_proxy(proxy, ptype):
    try:
        proxy_url = f"{ptype}://{proxy}"
        proxies = {"http": proxy_url, "https": proxy_url}
        response = requests.get(TEST_URL, proxies=proxies, timeout=5)
        if response.status_code == 200:
            return proxy_url
    except:
        return None

def filter_proxies(proxy_list):
    working = []
    threads = []

    def worker(proxy, ptype):
        result = test_proxy(proxy, ptype)
        if result:
            working.append(result)

    for proxy, ptype in proxy_list:
        t = threading.Thread(target=worker, args=(proxy, ptype))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
    return working

# ─── Telegram /start Command ─────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Fetching & testing proxies... Please wait ⏳")
    proxies = fetch_proxies()
    working = filter_proxies(proxies)

    if not working:
        await update.message.reply_text("❌ No working proxies found.")
        return

    with open("working_proxies.txt", "w") as f:
        for proxy in working:
            f.write(proxy + "\n")

    await update.message.reply_document(open("working_proxies.txt", "rb"))

# ─── Main ────────────────────────────────────
def main():
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.run_polling()

if __name__ == "__main__":
    main()
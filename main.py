import requests
import threading
import time
import logging
import os
import asyncio
import aiohttp
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
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&timeout=5000", "auto"),
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all", "http"),
    ("https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", "http"),
    ("https://proxylist.geonode.com/api/proxy-list?limit=300&page=1", "geonode"),
]

TEST_URLS = [
    "http://httpbin.org/ip",
    "http://www.google.com",
    "http://www.cloudflare.com"
]
TIMEOUT = 5
CONCURRENT_TESTS = 200

# ─── Flask Server to stay alive ─────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!", 200

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# Start Flask in a separate thread
threading.Thread(target=run_flask, daemon=True).start()

# ─── Fast Fetch Proxies with Async ──────────
async def fetch_proxies_async():
    all_proxies = []
    logging.info("[⚡] Fast fetching proxies with async...")
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url, ptype in PROXY_SOURCES:
            tasks.append(fetch_single_source(session, url, ptype))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                logging.warning(f"[✖] Error in async fetch: {result}")
            elif result:
                all_proxies.extend(result)
    
    # Remove duplicates
    unique_proxies = list(set(all_proxies))
    logging.info(f"[✔] Total unique proxies fetched: {len(unique_proxies)}")
    return unique_proxies

async def fetch_single_source(session, url, ptype):
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                proxies = []
                
                if "geonode" in ptype:
                    try:
                        json_data = await response.json()
                        proxies = [
                            (f"{item['ip']}:{item['port']}", item.get('protocols', ['http'])[0])
                            for item in json_data.get('data', [])
                        ]
                    except:
                        pass
                elif url.startswith("https://api.proxyscrape.com/v4/"):
                    raw_list = text.splitlines()
                    for line in raw_list:
                        if "://" in line:
                            proto, addr = line.split("://", 1)
                            proxies.append((addr.strip(), proto.strip()))
                        elif ":" in line:
                            proxies.append((line.strip(), "http"))
                else:
                    raw_list = text.splitlines()
                    proxies = [(proxy.strip(), ptype) for proxy in raw_list if proxy.strip()]
                
                logging.info(f"[✔] Fetched {len(proxies)} from {url}")
                return proxies
    except Exception as e:
        logging.warning(f"[✖] Error fetching {url}: {e}")
    return []

# ─── Ultra-Fast Proxy Testing with Async ────
async def test_proxy_async(session, proxy, ptype):
    test_url = TEST_URLS[0]  # Use the fastest test URL
    
    if ptype == "auto":
        protocols = ["socks5", "socks4", "http"]
    else:
        protocols = [ptype]
    
    for protocol in protocols:
        try:
            proxy_url = f"{protocol}://{proxy}"
            async with session.get(
                test_url, 
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as response:
                if response.status == 200:
                    # Quick content check
                    text = await response.text()
                    if "origin" in text or response.status == 200:
                        return proxy_url
        except:
            continue
    return None

async def filter_proxies_async(proxy_list):
    working = []
    logging.info(f"[⚡] Testing {len(proxy_list)} proxies with async...")
    
    connector = aiohttp.TCPConnector(limit=CONCURRENT_TESTS, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for proxy, ptype in proxy_list:
            tasks.append(test_proxy_async(session, proxy, ptype))
        
        # Process in chunks to avoid memory issues
        chunk_size = 500
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i + chunk_size]
            results = await asyncio.gather(*chunk, return_exceptions=True)
            
            for result in results:
                if result and not isinstance(result, Exception):
                    working.append(result)
            
            logging.info(f"[📊] Chunk {i//chunk_size + 1}: {len(working)} working so far")
    
    return working

# ─── Telegram /start Command ─────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    await update.message.reply_text("⚡ Fetching & testing proxies at high speed...")
    
    # Fetch proxies
    proxies = await fetch_proxies_async()
    
    if not proxies:
        await update.message.reply_text("❌ No proxies found.")
        return
    
    # Test proxies
    working = await filter_proxies_async(proxies)
    
    if not working:
        await update.message.reply_text("❌ No working proxies found.")
        return

    # Save to file
    with open("working_proxies.txt", "w") as f:
        for proxy in working:
            f.write(proxy + "\n")

    elapsed = time.time() - start_time
    await update.message.reply_text(
        f"✅ Found {len(working)} working proxies in {elapsed:.1f}s!\n"
        f"📊 Success rate: {(len(working)/len(proxies)*100):.1f}%"
    )
    await update.message.reply_document(
        document=open("working_proxies.txt", "rb"),
        caption=f"{len(working)} working proxies"
    )

# ─── Main ────────────────────────────────────
def main():
    if not BOT_TOKEN:
        logging.error("❌ BOT_TOKEN environment variable not set!")
        return
    
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    logging.info("🤖 Bot is starting with high-speed proxy testing...")
    app_bot.run_polling()

if __name__ == "__main__":
    main()

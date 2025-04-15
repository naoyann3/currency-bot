import discord
from discord.ext import commands
import requests
import re
import os
import time
import json
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_CHANNEL_IDS = [
    1010942568550387713,  # テスト一般会員部屋サポートライン
    1010942630324076634,  # テスト一般会員部屋レジスタンスライン
    949289154498408459,   # 運営部屋運営ボイチャ雑談
    1040300184795623444,  # 運営部屋全般改善部屋
    981557309526384753,   # 会員部屋レジスタンス部屋
    981557399032823869,   # 会員部屋サポート部屋
    1360244219486273674,  # 会員部屋サポートラインメンバー確認
    1360265671656739058   # 会員部屋レジスタンスライン確認部屋
]

ERROR_NOTIFY_CHANNEL_ID = 949289154498408459
PROCESSED_MESSAGE_IDS = set()
LAST_RATE = None
LAST_RATE_TIME = None
RATE_CACHE_DURATION = 300  # 5分（秒）

async def notify_error(channel_id, error_message):
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(f"⚠ Botエラー通知: {error_message}")
        else:
            print(f"Debug: Error notification channel {channel_id} not found", flush=True)
    except Exception as e:
        print(f"Debug: Failed to send error notification: {e}", flush=True)

def get_usd_jpy_rate():
    global LAST_RATE, LAST_RATE_TIME
    current_time = datetime.utcnow()

    if LAST_RATE and LAST_RATE_TIME and (current_time - LAST_RATE_TIME).total_seconds() < RATE_CACHE_DURATION:
        print(f"Debug: Using cached rate: {LAST_RATE}", flush=True)
        return LAST_RATE

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey={api_key}"
    
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if "Realtime Currency Exchange Rate" not in data:
                print(f"Debug: Invalid API response: {json.dumps(data, indent=2)}", flush=True)
                raise ValueError("Invalid API response")
                
            rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
            LAST_RATE = rate
            LAST_RATE_TIME = current_time
            print(f"Debug: Fetched real-time rate: {rate}", flush=True)
            return rate
            
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"Debug: Attempt {attempt + 1} failed: {str(e)}, Status Code: {response.status_code if response else 'N/A'}", flush=True)
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                fallback_rate = LAST_RATE if LAST_RATE else 145.00
                print(f"Debug: All retries failed, using fallback rate {fallback_rate}", flush=True)
                LAST_RATE = fallback_rate
                LAST_RATE_TIME = current_time
                bot.loop.create_task(notify_error(ERROR_NOTIFY_CHANNEL_ID, f"APIエラー: レート取得失敗、フォールバック {fallback_rate} を使用"))
                return fallback_rate

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！(鉄壁版)", flush=True)

@bot.event
async def on_message(message):
    if message.author == bot.user or message.id in PROCESSED_MESSAGE_IDS:
        return
    PROCESSED_MESSAGE_IDS.add(message.id)

    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        print(f"Debug: Skipped message in channel {message.channel.id} ({message.channel.name}), ID: {message.id}, Content: {message.content[:100]}...", flush=True)
        await bot.process_commands(message)
        return

    content = message.content
    dollar_pattern = r"(\d+)ドル"
    cme_pattern = r"CME窓[　\s]+赤丸(\d+)(?![ドル])"

    print(f"Debug: Processing message in channel {message.channel.id} ({message.channel.name}), ID: {message.id}", flush=True)
    print(f"Debug: Received message: {content[:100]}...", flush=True)

    rate = get_usd_jpy_rate()
    new_content = content.replace("@everyone", "").strip()
    modified = False
    avg_price_pos = new_content.find("平均取得単価")
    first_dollar = True

    def replace_dollar(match):
        nonlocal modified, first_dollar
        amount_str = match.group(1)
        print(f"Debug: Found dollar amount: {amount_str}", flush=True)
        try:
            amount_float = float(amount_str)
            result = int(amount_float * rate)
            amount_formatted = "{:,}".format(int(amount_float))
            result_formatted = "{:,}".format(result)
            modified = True
            base_output = f"{result_formatted}円\n{amount_formatted}ドル"
            if first_dollar:
                first_dollar = False
                return f"{base_output}\n(レート: 1ドル = {rate:.2f}円)"
            elif avg_price_pos != -1 and match.start() > avg_price_pos and "平均取得単価" in new_content[:match.start()]:
                return f"{result_formatted}円\n{amount_formatted}ドル"
            return base_output
        except ValueError as e:
            print(f"Debug: Invalid amount {amount_str}: {e}", flush=True)
            return match.group(0)

    new_content = re.sub(dollar_pattern, replace_dollar, new_content)
    if modified:
        print("Debug: Dollar amounts replaced", flush=True)

    def replace_cme(match):
        nonlocal modified
        amount_str = match.group(1)
        print(f"Debug: Found CME amount: {amount_str}", flush=True)
        try:
            amount_float = float(amount_str)
            result = int(amount_float * rate)
            amount_formatted = "{:,}".format(int(amount_float))
            result_formatted = "{:,}".format(result)
            modified = True
            return f"{result_formatted}円\nCME窓 赤丸{amount_formatted}ドル"
        except ValueError as e:
            print(f"Debug: Invalid amount {amount_str}: {e}", flush=True)
            return match.group(0)

    new_content = re.sub(cme_pattern, replace_cme, new_content)

    if not modified:
        print("Debug: No modifications made, skipping send", flush=True)
        await bot.process_commands(message)
        return

    new_content = new_content.replace("平均取得単価  ", "平均取得単価　")
    new_content = new_content.replace("平均取得単価   ", "平均取得単価　")

    final_content = new_content
    print(f"Debug: Sending message in channel {message.channel.id} ({message.channel.name}): {final_content[:100]}...", flush=True)
    await message.channel.send(final_content)

    await bot.process_commands(message)

bot.run(os.getenv("YOUR_BOT_TOKEN"))
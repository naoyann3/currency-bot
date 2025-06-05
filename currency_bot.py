import discord
from discord.ext import commands
import requests
import re
import os
import json
from datetime import datetime
import time

# Discordボット設定
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

PROCESSED_MESSAGE_IDS_FILE = "processed_message_ids.json"
PROCESSED_MESSAGE_IDS = set()  # 起動ごとに初期化
LAST_SKIPPED_MESSAGE_ID = None
LAST_RATE = None
LAST_RATE_TIME = None
RATE_CACHE_DURATION = 900  # 15分（秒）

async def notify_error(error_message):
    channel = bot.get_channel(949289154498408459)  # 運営ボイチャ雑談
    if channel:
        await channel.send(f"Botエラー: {error_message}\n詳細ログを確認してください: Renderダッシュボード")
    else:
        print(f"Debug: Failed to find channel 949289154498408459 for error notification", flush=True)

def save_processed_message_ids(message_ids):
    try:
        with open(PROCESSED_MESSAGE_IDS_FILE, "w") as f:
            json.dump(list(message_ids), f)
    except Exception as e:
        print(f"Debug: Error saving processed IDs: {e}", flush=True)

def get_usd_jpy_rate():
    global LAST_RATE, LAST_RATE_TIME
    now = datetime.now()
    if LAST_RATE and LAST_RATE_TIME and (now - LAST_RATE_TIME).total_seconds() < RATE_CACHE_DURATION:
        print(f"Debug: Using cached rate: {LAST_RATE}", flush=True)
        return LAST_RATE

    # Alpha Vantage（優先）
    for attempt in range(2):
        try:
            url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey={os.getenv('ALPHA_VANTAGE_API_KEY')}"
            response = requests.get(url, timeout=10)
            data = response.json()
            print(f"Debug: Raw API response: {data}", flush=True)
            if "Realtime Currency Exchange Rate" not in data or "5. Exchange Rate" not in data["Realtime Currency Exchange Rate"]:
                error_message = f"Invalid Alpha Vantage response: {data.get('Error Message', 'Unknown error')}, response: {response.text}"
                bot.loop.create_task(notify_error(error_message))
                raise ValueError(error_message)
            rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
            if not isinstance(rate, (int, float)):
                error_message = f"Invalid JPY rate type: {type(rate)}, response: {response.text}"
                bot.loop.create_task(notify_error(error_message))
                raise ValueError(error_message)
            print(f"Debug: Fetched real-time rate: {rate}", flush=True)
            LAST_RATE = rate
            LAST_RATE_TIME = now
            return rate
        except Exception as e:
            error_message = f"Alpha Vantage error (attempt {attempt+1}): {str(e)}, response: {response.text if 'response' in locals() else 'N/A'}"
            print(f"Debug: {error_message}", flush=True)
            if attempt == 0:
                time.sleep(1)
                continue
            bot.loop.create_task(notify_error(error_message))
            break

    # ExchangeRate-API（無料V6、バックアップ）
    for attempt in range(2):
        try:
            url = "https://v6.exchangerate-api.com/v6/latest/USD"
            response = requests.get(url, timeout=10)
            data = response.json()
            print(f"Debug: Raw API response: {data}", flush=True)
            if "conversion_rates" not in data or "JPY" not in data["conversion_rates"]:
                error_message = f"Invalid ExchangeRate-API response: {data.get('error', 'Unknown error')}, response: {response.text}"
                bot.loop.create_task(notify_error(error_message))
                raise ValueError(error_message)
            rate = float(data["conversion_rates"]["JPY"])
            if not isinstance(rate, (int, float)):
                error_message = f"Invalid JPY rate type: {type(rate)}, response: {response.text}"
                bot.loop.create_task(notify_error(error_message))
                raise ValueError(error_message)
            print(f"Debug: Fetched real-time rate: {rate}", flush=True)
            LAST_RATE = rate
            LAST_RATE_TIME = now
            return rate
        except Exception as e:
            error_message = f"ExchangeRate-API error (attempt {attempt+1}): {str(e)}, response: {response.text if 'response' in locals() else 'N/A'}"
            print(f"Debug: {error_message}", flush=True)
            if attempt == 0:
                time.sleep(1)
                continue
            bot.loop.create_task(notify_error(error_message))
            # 直近レートがあれば使用
            if LAST_RATE and LAST_RATE_TIME:
                print(f"Debug: Using last known rate: {LAST_RATE}", flush=True)
                return LAST_RATE
            LAST_RATE = 150.00
            LAST_RATE_TIME = now
            return 150.00

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！(鉄壁版)", flush=True)

@bot.event
async def on_message(message):
    global LAST_SKIPPED_MESSAGE_ID
    print(f"Debug: Checking message ID: {message.id}", flush=True)
    if message.author == bot.user or message.id in PROCESSED_MESSAGE_IDS:
        print(f"Debug: Skipping processed message ID: {message.id}", flush=True)
        return
    PROCESSED_MESSAGE_IDS.add(message.id)
    save_processed_message_ids(PROCESSED_MESSAGE_IDS)

    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        if LAST_SKIPPED_MESSAGE_ID != message.id:
            print(f"Debug: Skipped message in channel {message.channel.id} ({message.channel.name}), ID: {message.id}, Content: {message.content[:100]}...", flush=True)
            LAST_SKIPPED_MESSAGE_ID = message.id
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

# Discordボット起動
bot.run(os.getenv("YOUR_BOT_TOKEN"))

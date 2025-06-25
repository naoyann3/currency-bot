import discord
from discord.ext import commands
import requests
import re
import os
import json
from datetime import datetime
import time
import random

# Discordボット設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# エラーメッセージ抑制フラグ
SUPPRESS_ALPHA_VANTAGE_ERROR = True  # TrueでAlpha Vantageエラーメッセージをチャンネルに送信しない

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
RATE_CACHE_FILE = "rate_cache.json"
PROCESSED_MESSAGE_IDS = set()

# 起動時にprocessed_message_ids.jsonを読み込み
try:
    with open(PROCESSED_MESSAGE_IDS_FILE, "r") as f:
        PROCESSED_MESSAGE_IDS.update(set(json.load(f)))
except (FileNotFoundError, json.JSONDecodeError):
    pass  # ファイルがない場合は無視

LAST_SKIPPED_MESSAGE_ID = None
LAST_RATE = None
LAST_RATE_TIME = None
RATE_CACHE_DURATION = 900  # 15分（秒）
ALPHA_VANTAGE_KEYS = os.getenv("ALPHA_VANTAGE_KEYS", "").split(",")

async def notify_error(error_message, error_type="unknown"):
    channel = bot.get_channel(949289154498408459)  # 運営ボイチャ雑談
    if channel:
        if error_type == "invalid_key":
            message = (
                "【為替ボットからのお知らせ】\n"
                "ごめんね、ちょっとトラブル発生！😅 為替データのサービスキーが使えなくなったみたい。"
                "でも大丈夫、ボットは予備データ（1ドル=146.3374円）で動いてます！"
                "運営が新しいキーを準備するので、慌てなくてOKです！🙌 また報告します～！"
            )
        elif error_type == "connection_error":
            message = (
                "【為替ボットからのお知らせ】\n"
                "ごめんね、ちょっとトラブル発生！😅 為替データのサイトに繋がりにくくなっちゃったみたい。"
                "でも大丈夫、ボットは予備データ（1ドル=146.3374円）で動いてます！"
                "運営が後で確認するので、慌てなくてOKです！🙌 また報告します～！"
            )
        elif error_type == "rate_limit_exceeded":
            message = (
                "【為替ボットからのお知らせ】\n"
                "ごめんね、ちょっとトラブル発生！😅 為替データのサービスが混雑してるみたい。"
                "でも大丈夫、ボットは予備データ（1ドル=146.3374円）で動いてます！"
                "運営が後で確認するので、慌てなくてOKです！🙌 また報告します～！"
            )
        else:  # その他のエラー
            message = (
                "【為替ボットからのお知らせ】\n"
                "ごめんね、ちょっとトラブル発生！😅 為替データの取得で何か問題が起きたみたい。"
                "でも大丈夫、ボットは予備データ（1ドル=146.3374円）で動いてます！"
                "運営がゆっくりチェックするので、慌てなくてOKです！🙌 また報告します～！"
            )
        await channel.send(message)
    else:
        print(f"Debug: Failed to find channel 949289154498408459 for error notification", flush=True)
    print(f"Debug: Error details: {error_message}", flush=True)

def save_processed_message_ids(message_ids):
    try:
        with open(PROCESSED_MESSAGE_IDS_FILE, "w") as f:
            json.dump(list(message_ids), f)
    except Exception as e:
        print(f"Debug: Error saving processed IDs: {e}", flush=True)

def save_rate_cache(rate, timestamp):
    try:
        with open(RATE_CACHE_FILE, "w") as f:
            json.dump({"rate": rate, "timestamp": timestamp.isoformat()}, f)
    except Exception as e:
        print(f"Debug: Error saving rate cache: {e}", flush=True)

def load_rate_cache():
    try:
        if os.path.exists(RATE_CACHE_FILE):
            with open(RATE_CACHE_FILE, "r") as f:
                data = json.load(f)
            timestamp = datetime.fromisoformat(data["timestamp"])
            if (datetime.now() - timestamp).total_seconds() < 12 * 3600:  # 12時間有効
                return float(data["rate"])
    except Exception as e:
        print(f"Debug: Error loading rate cache: {e}", flush=True)
    return None

def get_usd_jpy_rate():
    global LAST_RATE, LAST_RATE_TIME
    now = datetime.now()
    if LAST_RATE and LAST_RATE_TIME and (now - LAST_RATE_TIME).total_seconds() < RATE_CACHE_DURATION:
        print(f"Debug: Using cached rate: {LAST_RATE}", flush=True)
        return LAST_RATE

    cached_rate = load_rate_cache()
    if cached_rate:
        LAST_RATE = cached_rate
        LAST_RATE_TIME = now
        print(f"Debug: Using file-cached rate: {LAST_RATE}", flush=True)
        return LAST_RATE

    # Alpha Vantage（優先）
    rate = None
    if not ALPHA_VANTAGE_KEYS or ALPHA_VANTAGE_KEYS == [""]:
        error_message = "No valid Alpha Vantage API keys provided in ALPHA_VANTAGE_KEYS"
        print(f"Debug: {error_message}", flush=True)
        if not SUPPRESS_ALPHA_VANTAGE_ERROR:
            bot.loop.create_task(notify_error(error_message, error_type="invalid_key"))
    else:
        print(f"Debug: Available Alpha Vantage keys: {ALPHA_VANTAGE_KEYS}", flush=True)
        available_keys = ALPHA_VANTAGE_KEYS.copy()  # キーリストのコピー
        attempts_per_key = 2
        while available_keys:
            try:
                key = random.choice(available_keys)
                print(f"Debug: Selected key: {key}", flush=True)
                url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=JPY&apikey={key}"
                response = requests.get(url, timeout=10)
                print(f"Debug: Response status: {response.status_code}", flush=True)
                if response.status_code == 429:
                    print(f"Debug: Rate limit exceeded for key: {key}, removing from available keys", flush=True)
                    available_keys.remove(key)  # リミット超過キーを除外
                    if not available_keys:
                        error_message = "All Alpha Vantage keys exceeded rate limit"
                        print(f"Debug: {error_message}", flush=True)
                        if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                            bot.loop.create_task(notify_error(error_message, error_type="rate_limit_exceeded"))
                    continue
                data = response.json()
                print(f"Debug: Raw API response (key: {key}): {data}", flush=True)
                if "Realtime Currency Exchange Rate" not in data or "5. Exchange Rate" not in data["Realtime Currency Exchange Rate"]:
                    error_message = f"Invalid Alpha Vantage response: {data.get('Information', 'Unknown error')}, response: {response.text}"
                    if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                        bot.loop.create_task(notify_error(error_message, error_type="invalid_key"))
                    raise ValueError(error_message)
                rate = float(data["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
                if not isinstance(rate, (int, float)):
                    error_message = f"Invalid JPY rate type: {type(rate)}, response: {response.text}"
                    if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                        bot.loop.create_task(notify_error(error_message, error_type="unknown"))
                    raise ValueError(error_message)
                print(f"Debug: Fetched real-time rate: {rate}", flush=True)
                break
            except requests.exceptions.RequestException as e:
                error_message = f"Alpha Vantage connection error (key: {key}): {str(e)}, response: {response.text if 'response' in locals() else 'N/A'}"
                print(f"Debug: {error_message}", flush=True)
                if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                    bot.loop.create_task(notify_error(error_message, error_type="connection_error"))
                available_keys.remove(key)  # 接続エラー時もキー除外
                if not available_keys:
                    error_message = "All Alpha Vantage keys failed due to connection errors"
                    print(f"Debug: {error_message}", flush=True)
                    if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                        bot.loop.create_task(notify_error(error_message, error_type="connection_error"))
            except Exception as e:
                error_message = f"Alpha Vantage error (key: {key}): {str(e)}, response: {response.text if 'response' in locals() else 'N/A'}"
                print(f"Debug: {error_message}", flush=True)
                if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                    bot.loop.create_task(notify_error(error_message, error_type="unknown"))
                available_keys.remove(key)  # その他のエラーでもキー除外
                if not available_keys:
                    error_message = "All Alpha Vantage keys failed due to unknown errors"
                    print(f"Debug: {error_message}", flush=True)
                    if not SUPPRESS_ALPHA_VANTAGE_ERROR:
                        bot.loop.create_task(notify_error(error_message, error_type="unknown"))

    # ExchangeRate-API（バックアップ）
    if rate is None:
        key = os.getenv("EXCHANGERATE_API_KEY")
        if not key:
            error_message = "No valid ExchangeRate-API key provided in EXCHANGERATE_API_KEY"
            print(f"Debug: {error_message}", flush=True)
            bot.loop.create_task(notify_error(error_message, error_type="invalid_key"))
        else:
            for attempt in range(2):
                try:
                    url = f"https://v6.exchangerate-api.com/v6/{key}/pair/USD/JPY"
                    response = requests.get(url, timeout=10)
                    data = response.json()
                    print(f"Debug: Raw API response (ExchangeRate-API, key: {key}): {data}", flush=True)
                    if data.get("result") != "success":
                        error_message = f"Invalid ExchangeRate-API response: {data.get('error-type', 'Unknown error')}, response: {response.text}"
                        bot.loop.create_task(notify_error(error_message, error_type="unknown"))
                        raise ValueError(error_message)
                    rate = float(data["conversion_rate"])
                    if not isinstance(rate, (int, float)):
                        error_message = f"Invalid JPY rate type: {type(rate)}, response: {response.text}"
                        bot.loop.create_task(notify_error(error_message, error_type="unknown"))
                        raise ValueError(error_message)
                    print(f"Debug: Fetched real-time rate: {rate}", flush=True)
                    break
                except requests.exceptions.RequestException as e:
                    error_message = f"ExchangeRate-API connection error (attempt {attempt+1}, key: {key}): {str(e)}, response: {response.text if 'response' in locals() else 'N/A'}"
                    print(f"Debug: {error_message}", flush=True)
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    bot.loop.create_task(notify_error(error_message, error_type="connection_error"))
                except Exception as e:
                    error_message = f"ExchangeRate-API error (attempt {attempt+1}, key: {key}): {str(e)}, response: {response.text if 'response' in locals() else 'N/A'}"
                    print(f"Debug: {error_message}", flush=True)
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    bot.loop.create_task(notify_error(error_message, error_type="unknown"))

    if rate is None:
        rate = load_rate_cache() or 150.00
        print(f"Debug: Using file-cached or default rate: {rate}", flush=True)
    else:
        save_rate_cache(rate, now)
    LAST_RATE = rate
    LAST_RATE_TIME = now
    return rate

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

import discord
from discord.ext import commands
import requests
import re
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_CHANNEL_IDS = [
    1010942568550387713,  # #btc-trading
    1010942630324076634   # #crypto-updates
    # テスト用に追加した分は後で削除可
]

def get_usd_jpy_rate():
    try:
        api_key = os.getenv("API_KEY")
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD"
        response = requests.get(url)
        data = response.json()
        rate = data["conversion_rates"]["JPY"]
        print(f"Debug: Fetched real-time rate: {rate}", flush=True)
        return rate
    except Exception as e:
        print(f"Debug: Error fetching rate: {e}, using fallback 146.59", flush=True)
        return 146.59

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！(複数チャンネル版)", flush=True)

@bot.event
async def on_message(message):
    # 重複処理防止
    if message.author == bot.user or hasattr(message, "_processed"):
        return
    message._processed = True  # 処理済みフラグをセット

    # チャンネルIDをチェック
    if message.channel.id not in ALLOWED_CHANNEL_IDS:
        print(f"Debug: Message from channel {message.channel.id}, skipping (not in {ALLOWED_CHANNEL_IDS})", flush=True)
        await bot.process_commands(message)
        return

    content = message.content
    dollar_pattern = r"(\d+)ドル"
    cme_pattern = r"CME窓[　\s]+赤丸(\d+)(?![ドル])"

    print(f"Debug: Received message: {content[:100]}...", flush=True)

    is_support = "サポートライン" in content
    is_resistance = "レジスタンスライン" in content
    direction = "より上" if is_support else "より下" if is_resistance else "付近"
    print(f"Debug: is_support={is_support}, is_resistance={is_resistance}, direction={direction}", flush=True)

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
            base_output = f"{result_formatted}円{direction}\n{amount_formatted}ドル"
            if first_dollar:
                first_dollar = False
                return f"{base_output}\n(レート: 1ドル = {rate:.2f}円)"
            elif avg_price_pos != -1 and match.start() > avg_price_pos and "平均取得単価" in new_content[:match.start()]:
                return f"{result_formatted}円{direction}\n{amount_formatted}ドル"
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
        amount_float = float(amount_str)
        result = int(amount_float * rate)
        amount_formatted = "{:,}".format(int(amount_float))
        result_formatted = "{:,}".format(result)
        modified = True
        return f"{result_formatted}円{direction}\nCME窓 赤丸{amount_formatted}ドル"

    new_content = re.sub(cme_pattern, replace_cme, new_content)

    if not modified:
        print("Debug: No modifications made, skipping send", flush=True)
        await bot.process_commands(message)
        return

    new_content = new_content.replace("平均取得単価  ", "平均取得単価　")
    new_content = new_content.replace("平均取得単価   ", "平均取得単価　")

    final_content = "@everyone\n" + new_content
    print("Debug: Sending final content", flush=True)
    
    try:
        await message.delete()
        print("Debug: Original message deleted", flush=True)
    except Exception as e:
        print(f"Debug: Failed to delete message: {e}", flush=True)
    
    await message.channel.send(final_content)

    await bot.process_commands(message)

bot.run(os.getenv("YOUR_BOT_TOKEN"))
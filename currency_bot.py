import discord
from discord.ext import commands
import requests
import re
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def get_usd_jpy_rate():
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    try:
        response = requests.get(url)
        data = response.json()
        rate = data["rates"]["JPY"]
        print(f"Debug: Rate fetched successfully: {rate}", flush=True)
        return rate
    except Exception as e:
        print(f"Debug: Rate fetch failed: {e}", flush=True)
        return 146.59

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！(再確認版)", flush=True)

@bot.event
async def on_message(message):
    if message.author == bot.user:
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

    # 通常の「◯◯ドル」の置換
    def replace_dollar(match):
        nonlocal modified
        amount_str = match.group(1)
        print(f"Debug: Found dollar amount: {amount_str}", flush=True)
        try:
            amount_float = float(amount_str)
            result = int(amount_float * rate)
            amount_formatted = "{:,}".format(int(amount_float))
            result_formatted = "{:,}".format(result)
            modified = True
            return f"{result_formatted}円{direction}\n{amount_formatted}ドル"
        except ValueError as e:
            print(f"Debug: Invalid amount {amount_str}: {e}", flush=True)
            return match.group(0)

    new_content = re.sub(dollar_pattern, replace_dollar, new_content)
    if modified:
        print("Debug: Dollar amounts replaced", flush=True)

    # 「CME窓 赤丸◯◯」の置換
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

    # レートを「平均取得単価」の直下に挿入
    avg_price_pos = new_content.find("平均取得単価")
    if avg_price_pos != -1:
        # 「平均取得単価」の次の改行位置を探す
        next_newline = new_content.find("\n", avg_price_pos)
        if next_newline == -1:
            new_content += f"\n(レート: 1ドル = {rate:.2f}円)"
        else:
            new_content = (
                new_content[:next_newline] +
                f"\n(レート: 1ドル = {rate:.2f}円)" +
                new_content[next_newline:]
            )
    else:
        new_content += f"\n(レート: 1ドル = {rate:.2f}円)"

    final_content = "@everyone\n" + new_content
    print("Debug: Sending final content", flush=True)
    await message.channel.send(final_content)

    await bot.process_commands(message)

bot.run(os.getenv("YOUR_BOT_TOKEN"))

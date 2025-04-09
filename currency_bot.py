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
    response = requests.get(url)
    data = response.json()
    return data["rates"]["JPY"]

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！(再確認版)")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content
    dollar_pattern = r"(\d+)ドル"
    cme_pattern = r"CME窓[　\s]+赤丸(\d+)(?![ドル])"

    # サポートかレジスタンスかを判定
    is_support = "サポートライン" in content
    is_resistance = "レジスタンスライン" in content
    direction = "より上" if is_support else "より下" if is_resistance else "付近"

    matches = re.search(dollar_pattern, content) or re.search(cme_pattern, content)
    if not matches:
        await bot.process_commands(message)
        return

    rate = get_usd_jpy_rate()
    new_content = content.replace("@everyone", "").strip()

    # 通常の「◯◯ドル」の処理
    for match in re.finditer(dollar_pattern, new_content):
        amount_str = match.group(1)
        amount_float = float(amount_str)
        result = int(amount_float * rate)
        amount_formatted = "{:,}".format(int(amount_float))
        result_formatted = "{:,}".format(result)
        if "平均取得単価" in new_content and amount_str in new_content.split("平均取得単価")[1]:
            new_content = new_content.replace(f"{amount_str}ドル", f"{amount_formatted}ドル", 1)
        else:
            new_content = new_content.replace(f"{amount_str}ドル", f"{result_formatted}円{direction}\n{amount_formatted}ドル", 1)

    # 「CME窓 赤丸◯◯」の処理
    for match in re.finditer(cme_pattern, new_content):
        amount_str = match.group(1)
        amount_float = float(amount_str)
        result = int(amount_float * rate)
        amount_formatted = "{:,}".format(int(amount_float))
        result_formatted = "{:,}".format(result)
        new_content = new_content.replace(
            match.group(0),
            f"{result_formatted}円{direction}\nCME窓 赤丸{amount_formatted}ドル",
            1
        )

    # レート情報
    if "平均取得単価" in new_content:
        new_content = new_content.replace(
            "平均取得単価",
            f"平均取得単価\n(レート: 1ドル = {rate:.2f}円)",
            1
        )
    else:
        new_content += f"\n(レート: 1ドル = {rate:.2f}円)"

    final_content = "@everyone\n" + new_content
    await message.channel.send(final_content)

    await bot.process_commands(message)

bot.run(os.getenv("YOUR_BOT_TOKEN"))

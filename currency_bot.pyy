import discord
import os
from discord.ext import commands
import requests
import re

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！")

@bot.command()
async def usd(ctx):
    lines = ctx.message.content.split("\n")
    if not lines:
        await ctx.send("金額を入力してください（例: !usd 79000ドル）")
        return

    url = "https://api.exchangerate-api.com/v4/latest/USD"
    response = requests.get(url)
    data = response.json()
    rate = data["rates"]["JPY"]

    results = []
    for line in lines:
        amount_str = line.replace("!usd", "").strip()
        if not amount_str:
            continue
        try:
            amount_cleaned = ''.join(filter(str.isdigit, amount_str))
            if not amount_cleaned:
                continue
            amount_float = float(amount_cleaned)
            result = int(amount_float * rate)
            amount_formatted = "{:,}".format(int(amount_float))
            result_formatted = "{:,}".format(result)
            results.append(f"{amount_formatted}ドル = {result_formatted}円")
        except ValueError:
            results.append(f"'{amount_str}' は数値として認識できません")

    if not results:
        await ctx.send("有効な金額が見つかりませんでした")
        return
    output = "\n".join(results) + f"\n(レート: 1ドル = {rate}円)"
    await ctx.send(output)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    content = message.content
    dollar_pattern = r"(\d+)ドル"
    cme_pattern = r"CME窓[　\s]+赤丸(\d+)(?![ドル])"
    matches = re.search(dollar_pattern, content) or re.search(cme_pattern, content)
    if not matches:
        await bot.process_commands(message)
        return

    url = "https://api.exchangerate-api.com/v4/latest/USD"
    response = requests.get(url)
    data = response.json()
    rate = data["rates"]["JPY"]

    # @everyoneを削除した内容を処理
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
            new_content = new_content.replace(f"{amount_str}ドル", f"{result_formatted}円より上\n{amount_formatted}ドル", 1)

    # 「CME窓 赤丸◯◯」の処理
    for match in re.finditer(cme_pattern, new_content):
        amount_str = match.group(1)
        amount_float = float(amount_str)
        result = int(amount_float * rate)
        amount_formatted = "{:,}".format(int(amount_float))
        result_formatted = "{:,}".format(result)
        new_content = new_content.replace(
            match.group(0),
            f"{result_formatted}円より上\nCME窓 赤丸{amount_formatted}ドル",
            1
        )

    # 「平均取得単価」の後にレート情報を挿入
    avg_price_pattern = r"ストラテジー平均取得単価\s+([\d,]+ドル)"
    if re.search(avg_price_pattern, new_content):
        new_content = re.sub(
            avg_price_pattern,
            r"ストラテジー平均取得単価　\1\n(レート: 1ドル = " + str(rate) + "円)",
            new_content
        )
    else:
        # 見つからない場合は文末に追加（念のため）
        new_content += f"\n(レート: 1ドル = {rate}円)"

    # 文頭に@everyoneを追加
    final_content = "@everyone\n" + new_content
    await message.channel.send(final_content)

    await bot.process_commands(message)

bot.run(os.getenv("YOUR_BOT_TOKEN"))

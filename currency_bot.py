import discord
import os
import requests
import re
from discord.ext import commands

# Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 為替レートを取得
def get_usd_jpy_rate():
    url = "https://finance.yahoo.co.jp/quote/USDJPY=FX"
    response = requests.get(url)
    text = response.text
    match = re.search(r'<span class="_3-31US8F">([\d.]+)</span>', text)
    if match:
        return float(match.group(1))
    return 146.59  # デフォルト値

# 起動時
@bot.event
async def on_ready():
    print(f'{bot.user} が起動しました！')

# コマンド
@bot.command()
async def rate(ctx, *, message):
    rate = get_usd_jpy_rate()
    lines = message.split('\n')
    output = ["@everyone", "メンバー限定情報"]

    # サポートかレジスタンスかを判定
    is_support = "サポートライン" in message
    is_resistance = "レジスタンスライン" in message
    if is_support:
        output.append("BTC　サポートライン")
        direction = "より上"
    elif is_resistance:
        output.append("BTC　レジスタンスライン")
        direction = "より下"
    else:
        output.append("BTC　ライン（未指定）")
        direction = "付近"  # どちらでもない場合のデフォルト
    output.append("")

    # 価格を抽出して変換
    prices = []
    for line in lines:
        match = re.search(r'(\d{5,6})\s*ドル', line)
        if match:
            usd_price = int(match.group(1).replace(',', ''))
            jpy_price = int(usd_price * rate)
            prices.append(f"{jpy_price:,}円{direction}\n{usd_price:,}ドル")
        else:
            output.append(line)

    # 価格を挿入
    for i, line in enumerate(output):
        if "短期トレード資金の現金保有率が低い" in line:
            output[i+1:i+1] = prices
            break

    output.append(f"(レート: 1ドル = {rate:.2f}円)")
    await ctx.send('\n'.join(output))

bot.run(os.getenv("YOUR_BOT_TOKEN"))

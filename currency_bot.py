import discord
from discord.ext import commands
import requests
import re
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_CHANNEL_IDS = [
    1010942568550387713,  # #btc-trading
    1010942630324076634,
    949289154498408459,
    1040300184795623444            # #crypto-updates
]
PROCESSED_MESSAGE_IDS = set()

def get_usd_jpy_rate():
    # (省略: 前と同じ)
    pass

@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました！(鉄壁版)", flush=True)

@bot.event
async def on_message(message):
    # (省略: 前と同じ)
    pass

async def main():
    async with bot:
        while True:
            try:
                await bot.start(os.getenv("YOUR_BOT_TOKEN"))
            except Exception as e:
                print(f"Error: {e}, retrying in 5 seconds...", flush=True)
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
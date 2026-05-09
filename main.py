# Fixed Roblox Tracker Bot (2 Minute Early Alerts)

Replace your current code with this:

```python
import os
import time
import json
import asyncio
import threading
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask

# =========================================================
# WEB SERVER
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Online"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE")

PLACE_ID = 13358463560
CHECK_INTERVAL = 5
DATA_FILE = "servers.json"

RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

# 2 MINUTES EARLY
WARNING_BEFORE = 120

# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# DATABASE
# =========================================================


def load_data():

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)

    return {}


server_database = load_data()



def save_data():

    with open(DATA_FILE, "w") as f:
        json.dump(server_database, f, indent=4)

# =========================================================
# ROBLOX API
# =========================================================

BASE_URL = (
    f"https://games.roblox.com/v1/games/"
    f"{PLACE_ID}/servers/Public?limit=100"
)


async def fetch_servers():

    servers = []
    cursor = None

    async with aiohttp.ClientSession() as session:

        while True:

            url = BASE_URL

            if cursor:
                url += f"&cursor={cursor}"

            try:

                async with session.get(url) as response:

                    if response.status != 200:
                        print("API ERROR", response.status)
                        break

                    data = await response.json()

                    servers.extend(data.get("data", []))

                    cursor = data.get("nextPageCursor")

                    if not cursor:
                        break

                    await asyncio.sleep(0.15)

            except Exception as e:
                print("FETCH ERROR", e)
                break

    return servers

# =========================================================
# GET REAL SERVER TIME
# =========================================================


async def get_server_age(server_id):

    url = "https://gamejoin.roblox.com/v1/join-game-instance"

    payload = {
        "placeId": PLACE_ID,
        "gameId": server_id,
        "gameJoinAttemptId": server_id
    }

    cookies = {
        ".ROBLOSECURITY": ROBLOX_COOKIE
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:

        async with aiohttp.ClientSession(
            cookies=cookies,
            headers=headers
        ) as session:

            async with session.post(url, json=payload) as response:

                if response.status != 200:
                    return None

                data = await response.json()

                join_script = data.get("joinScript", {})

                claimed_time = join_script.get("ServerClaimedTime")

                if not claimed_time:
                    return None

                current_ms = int(time.time() * 1000)

                age_seconds = (current_ms - claimed_time) // 1000

                return int(age_seconds)

    except Exception as e:
        print("AGE ERROR", e)
        return None

# =========================================================
# FORMAT TIME
# =========================================================


def format_time(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    return f"{hours}h {minutes}m"

# =========================================================
# MILESTONES
# =========================================================

RIFT_MILESTONES = []
BOSS_MILESTONES = []

rift = 5400

while rift <= 172800:
    RIFT_MILESTONES.append(rift)
    rift += 5400

boss = 7200

while boss <= 172800:
    BOSS_MILESTONES.append(boss)
    boss += 7200

# =========================================================
# TRACKER
# =========================================================

@tasks.loop(seconds=CHECK_INTERVAL)
async def server_tracker():

    current_time = int(time.time())

    print(f"[{datetime.utcnow()}] SCANNING")

    servers = await fetch_servers()

    live_servers = set()

    for server in servers:

        server_id = server["id"]

        live_servers.add(server_id)

        if server_id not in server_database:

            server_database[server_id] = {
                "last_seen": current_time,
                "rift_announced": [],
                "boss_announced": []
            }

        else:
            server_database[server_id]["last_seen"] = current_time

        # =============================================
        # REAL AGE
        # =============================================

        uptime = await get_server_age(server_id)

        if uptime is None:
            continue

        # REMOVE OLD SERVERS
        if uptime > 172800:
            continue

        join_link = (
            f"https://www.roblox.com/games/start?"
            f"placeId={PLACE_ID}"
            f"&gameInstanceId={server_id}"
        )

        # =============================================
        # RIFTS
        # =============================================

        for milestone in RIFT_MILESTONES:

            warning_time = milestone - WARNING_BEFORE

            if (
                uptime >= warning_time
                and uptime < warning_time + CHECK_INTERVAL
                and milestone not in server_database[server_id]["rift_announced"]
            ):

                channel = bot.get_channel(RIFT_CHANNEL_ID)

                if channel:

                    await channel.send(
                        f"🌀 **RIFT SPAWNING IN 2 MINUTES**\n\n"
                        f"⏱️ Spawn Time: `{format_time(milestone)}`\n"
                        f"📈 Current Server Age: `{format_time(uptime)}`\n"
                        f"🆔 Server ID: `{server_id}`\n\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id]["rift_announced"].append(milestone)

                print(f"RIFT {server_id} {milestone}")

        # =============================================
        # BOSSES
        # =============================================

        for milestone in BOSS_MILESTONES:

            warning_time = milestone - WARNING_BEFORE

            if (
                uptime >= warning_time
                and uptime < warning_time + CHECK_INTERVAL
                and milestone not in server_database[server_id]["boss_announced"]
            ):

                channel = bot.get_channel(BOSS_CHANNEL_ID)

                if channel:

                    await channel.send(
                        f"👹 **BOSS SPAWNING IN 2 MINUTES**\n\n"
                        f"⏱️ Spawn Time: `{format_time(milestone)}`\n"
                        f"📈 Current Server Age: `{format_time(uptime)}`\n"
                        f"🆔 Server ID: `{server_id}`\n\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id]["boss_announced"].append(milestone)

                print(f"BOSS {server_id} {milestone}")

    # =============================================
    # REMOVE DEAD SERVERS
    # =============================================

    remove_list = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if current_time - data["last_seen"] > 120:
                remove_list.append(server_id)

    for server_id in remove_list:
        del server_database[server_id]

    save_data()

    print(f"TRACKING {len(server_database)} SERVERS")

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong")


@bot.tree.command(name="tracked")
async def tracked(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Tracking {len(server_database)} servers"
    )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"LOGGED IN AS {bot.user}")

    if not server_tracker.is_running():
        server_tracker.start()

# =========================================================
# START
# =========================================================

threading.Thread(target=run_web).start()

bot.run(TOKEN)
```

# Environment Keys

Set these in Render:

## Key 1

DISCORD_TOKEN

Value:
Your Discord bot token

## Key 2

ROBLOX_COOKIE

Value:
Your full .ROBLOSECURITY cookie

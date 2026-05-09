import os
import time
import json
import asyncio
import threading
import uuid
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask

# =========================================================
# WEB SERVER (RENDER)
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Roblox Tracker Bot Online"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")
ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE")

PLACE_ID = 13358463560
CHECK_INTERVAL = 20
DATA_FILE = "servers.json"

# PUT YOUR CHANNEL IDS HERE
RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

# =========================================================
# DISCORD SETUP
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

def save_data():

    with open(DATA_FILE, "w") as f:
        json.dump(server_database, f, indent=4)

server_database = load_data()

# =========================================================
# ROBLOX API
# =========================================================

BASE_URL = (
    f"https://games.roblox.com/v1/games/"
    f"{PLACE_ID}/servers/Public?limit=100"
)

JOIN_URL = (
    "https://gamejoin.roblox.com/v1/join-game-instance"
)

# =========================================================
# FETCH PUBLIC SERVERS
# =========================================================

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

                        print(
                            f"Public API Error: {response.status}"
                        )

                        break

                    data = await response.json()

                    servers.extend(
                        data.get("data", [])
                    )

                    cursor = data.get(
                        "nextPageCursor"
                    )

                    if not cursor:
                        break

                    await asyncio.sleep(0.15)

            except Exception as e:

                print("Fetch Error:", e)
                break

    return servers

# =========================================================
# GET REAL SERVER UPTIME
# =========================================================

async def get_server_uptime(server_id):

    headers = {
        "Cookie": f".ROBLOSECURITY={ROBLOX_COOKIE}",
        "Content-Type": "application/json",
        "User-Agent": "Roblox/WinInet"
    }

    payload = {
        "placeId": PLACE_ID,
        "gameId": server_id,
        "gameJoinAttemptId": str(uuid.uuid4())
    }

    try:

        async with aiohttp.ClientSession() as session:

            async with session.post(
                JOIN_URL,
                headers=headers,
                json=payload
            ) as response:

                if response.status != 200:

                    print(
                        f"Join API Error: {response.status}"
                    )

                    text = await response.text()
                    print(text)

                    return None

                data = await response.json()

                join_script = data.get(
                    "joinScript",
                    {}
                )

                claimed_time = join_script.get(
                    "ServerClaimedTime"
                )

                if not claimed_time:

                    print(
                        f"No ServerClaimedTime for {server_id}"
                    )

                    return None

                current_ms = int(
                    time.time() * 1000
                )

                uptime_seconds = (
                    current_ms - claimed_time
                ) // 1000

                return int(uptime_seconds)

    except Exception as e:

        print(
            f"Uptime Fetch Error for {server_id}:",
            e
        )

        return None

# =========================================================
# TIME FORMATTER
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

    print(
        f"[{datetime.utcnow()}] "
        f"Scanning servers..."
    )

    servers = await fetch_servers()

    live_servers = set()

    for server in servers:

        server_id = server["id"]

        live_servers.add(server_id)

        print(f"Checking server {server_id}")

        uptime = await get_server_uptime(
            server_id
        )

        if uptime is None:
            continue

        join_link = (
            f"https://www.roblox.com/games/start?"
            f"placeId={PLACE_ID}"
            f"&gameInstanceId={server_id}"
        )

        if server_id not in server_database:

            server_database[server_id] = {
                "rift_announced": [],
                "boss_announced": [],
                "last_seen": current_time
            }

            print(
                f"[NEW SERVER] "
                f"{server_id}"
            )

        server_database[server_id]["last_seen"] = (
            current_time
        )

        # =================================================
        # RIFT ANNOUNCEMENTS
        # =================================================

        for milestone in RIFT_MILESTONES:

            if (
                uptime >= milestone
                and milestone not in
                server_database[server_id]["rift_announced"]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"🌀 **Rift Server Found**\n\n"
                        f"⏱️ Uptime: "
                        f"`{format_time(uptime)}`\n"
                        f"🆔 Server ID: "
                        f"`{server_id}`\n"
                        f"🔗 Join:\n"
                        f"{join_link}"
                    )

                server_database[server_id][
                    "rift_announced"
                ].append(milestone)

                print(
                    f"[RIFT] {server_id} "
                    f"{format_time(uptime)}"
                )

        # =================================================
        # BOSS ANNOUNCEMENTS
        # =================================================

        for milestone in BOSS_MILESTONES:

            if (
                uptime >= milestone
                and milestone not in
                server_database[server_id]["boss_announced"]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"👹 **Boss Server Found**\n\n"
                        f"⏱️ Uptime: "
                        f"`{format_time(uptime)}`\n"
                        f"🆔 Server ID: "
                        f"`{server_id}`\n"
                        f"🔗 Join:\n"
                        f"{join_link}"
                    )

                server_database[server_id][
                    "boss_announced"
                ].append(milestone)

                print(
                    f"[BOSS] {server_id} "
                    f"{format_time(uptime)}"
                )

    save_data()

    print(
        f"Tracking "
        f"{len(live_servers)} "
        f"live servers"
    )

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check if the bot is online"
)
async def ping(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "🏓 Pong!"
    )

# =========================================================
# READY EVENT
# =========================================================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(
        f"Logged in as {bot.user}"
    )

    if not server_tracker.is_running():
        server_tracker.start()

# =========================================================
# START EVERYTHING
# =========================================================

threading.Thread(
    target=run_web
).start()

bot.run(TOKEN)

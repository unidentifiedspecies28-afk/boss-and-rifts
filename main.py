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

RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

MAX_SERVER_AGE = 172800  # 48 hours

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

def save_data():

    with open(DATA_FILE, "w") as f:
        json.dump(server_database, f, indent=4)

server_database = load_data()

# =========================================================
# ROBLOX SERVER API
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
                        print(f"API Error: {response.status}")
                        break

                    data = await response.json()

                    servers.extend(data.get("data", []))

                    cursor = data.get("nextPageCursor")

                    if not cursor:
                        break

                    await asyncio.sleep(0.1)

            except Exception as e:
                print("Fetch Error:", e)
                break

    return servers

# =========================================================
# GET REAL SERVER CLAIMED TIME
# =========================================================

async def get_server_claimed_time(server_id):

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
        "Content-Type": "application/json",
        "Referer": f"https://www.roblox.com/games/{PLACE_ID}/"
    }

    try:

        async with aiohttp.ClientSession(
            cookies=cookies
        ) as session:

            async with session.post(
                url,
                json=payload,
                headers=headers
            ) as response:

                if response.status != 200:
                    print(
                        f"Claimed Time Error "
                        f"{server_id}: {response.status}"
                    )
                    return None

                data = await response.json()

                join_script = data.get("joinScript", {})

                claimed_time = join_script.get(
                    "ServerClaimedTime"
                )

                if claimed_time:
                    return int(claimed_time / 1000)

    except Exception as e:
        print("Claimed Time Error:", e)

    return None

# =========================================================
# TIME FORMATTER
# =========================================================

def format_time(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    return f"{hours}h {minutes}m {seconds}s"

# =========================================================
# SPAWN TIMES
# =========================================================

RIFT_TIMES = []
BOSS_TIMES = []

rift = 5400

while rift <= MAX_SERVER_AGE:
    RIFT_TIMES.append(rift)
    rift += 5400

boss = 7200

while boss <= MAX_SERVER_AGE:
    BOSS_TIMES.append(boss)
    boss += 7200

# =========================================================
# ALERT SETTINGS
# =========================================================

# 5 minutes before spawn
ALERT_BEFORE = 180

# allow small timing window
WINDOW = 5

# =========================================================
# TRACKER
# =========================================================

@tasks.loop(seconds=CHECK_INTERVAL)
async def server_tracker():

    global server_database

    current_time = int(time.time())

    print(f"[{datetime.utcnow()}] Scanning servers...")

    servers = await fetch_servers()

    live_servers = set()

    for server in servers:

        server_id = server["id"]

        live_servers.add(server_id)

        # =================================================
        # NEW SERVER
        # =================================================

        if server_id not in server_database:

            claimed_time = await get_server_claimed_time(
                server_id
            )

            if not claimed_time:
                claimed_time = current_time

            server_database[server_id] = {
                "claimed_time": claimed_time,
                "last_seen": current_time,
                "rift_sent": [],
                "boss_sent": []
            }

            print(
                f"[NEW SERVER] {server_id} "
                f"Claimed: {claimed_time}"
            )

        else:

            server_database[server_id][
                "last_seen"
            ] = current_time

        # =================================================
        # UPTIME
        # =================================================

        uptime = (
            current_time
            - server_database[server_id]["claimed_time"]
        )

        if uptime < 0:
            continue

        if uptime > MAX_SERVER_AGE:
            continue

        # =================================================
        # JOIN LINK
        # =================================================

        join_link = (
            f"https://www.roblox.com/games/start?"
            f"placeId={PLACE_ID}"
            f"&gameInstanceId={server_id}"
        )

        # =================================================
        # RIFT ALERTS
        # =================================================

        for spawn_time in RIFT_TIMES:

            remaining = spawn_time - uptime

            if (
                ALERT_BEFORE - WINDOW
                <= remaining
                <= ALERT_BEFORE + WINDOW
                and spawn_time not in
                server_database[server_id]["rift_sent"]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"🌀 **Rift Spawning Soon**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"🎯 Rift Spawns In: "
                        f"`{format_time(remaining)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "rift_sent"
                ].append(spawn_time)

                print(
                    f"[RIFT ALERT] {server_id} "
                    f"{format_time(spawn_time)}"
                )

        # =================================================
        # BOSS ALERTS
        # =================================================

        for spawn_time in BOSS_TIMES:

            remaining = spawn_time - uptime

            if (
                ALERT_BEFORE - WINDOW
                <= remaining
                <= ALERT_BEFORE + WINDOW
                and spawn_time not in
                server_database[server_id]["boss_sent"]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"👹 **Boss Spawning Soon**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"🎯 Boss Spawns In: "
                        f"`{format_time(remaining)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "boss_sent"
                ].append(spawn_time)

                print(
                    f"[BOSS ALERT] {server_id} "
                    f"{format_time(spawn_time)}"
                )

    # =====================================================
    # REMOVE DEAD SERVERS
    # =====================================================

    dead_servers = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if (
                current_time - data["last_seen"]
                > CHECK_INTERVAL * 3
            ):

                print(f"[REMOVED] {server_id}")

                dead_servers.append(server_id)

        else:

            uptime = (
                current_time
                - data["claimed_time"]
            )

            if uptime > MAX_SERVER_AGE:

                print(
                    f"[48H LIMIT] {server_id}"
                )

                dead_servers.append(server_id)

    for dead in dead_servers:

        if dead in server_database:
            del server_database[dead]

    save_data()

    print(
        f"Tracking {len(live_servers)} servers"
    )

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check bot status"
)
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🏓 Pong!"
    )

@bot.tree.command(
    name="tracked",
    description="Tracked server count"
)
async def tracked(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Tracking `{len(server_database)}` servers."
    )

@bot.tree.command(
    name="uptime",
    description="Check server uptime"
)
async def uptime(
    interaction: discord.Interaction,
    server_id: str
):

    if server_id not in server_database:

        await interaction.response.send_message(
            "❌ Server not tracked."
        )

        return

    uptime_seconds = (
        int(time.time())
        - server_database[server_id][
            "claimed_time"
        ]
    )

    await interaction.response.send_message(
        f"⏱️ Uptime: "
        f"`{format_time(uptime_seconds)}`"
    )

# =========================================================
# READY EVENT
# =========================================================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"Logged in as {bot.user}")

    if not server_tracker.is_running():
        server_tracker.start()

# =========================================================
# START
# =========================================================

threading.Thread(target=run_web).start()

bot.run(TOKEN)

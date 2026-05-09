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
# WEB SERVER
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

CHECK_INTERVAL = 30
DATA_FILE = "servers.json"

RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

MAX_SERVER_AGE = 172800  # 48 hours

# 5 minutes before spawn
ANNOUNCE_EARLY = 300

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

                    if response.status == 429:

                        print("Rate limited (429)")
                        await asyncio.sleep(10)
                        break

                    if response.status != 200:
                        print(f"API Error: {response.status}")
                        break

                    data = await response.json()

                    servers.extend(data.get("data", []))

                    cursor = data.get("nextPageCursor")

                    if not cursor:
                        break

                    await asyncio.sleep(0.25)

            except Exception as e:
                print("Fetch Error:", e)
                break

    return servers

# =========================================================
# GET CLAIMED TIME
# =========================================================

async def get_server_claimed_time(server_id):

    url = "https://gamejoin.roblox.com/v1/join-game-instance"

    payload = {
        "placeId": PLACE_ID,
        "gameId": server_id,
        "gameJoinAttemptId": str(uuid.uuid4())
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

                if response.status == 429:
                    print("Claimed time rate limited")
                    return None

                if response.status != 200:
                    return None

                data = await response.json()

                if not data:
                    return None

                join_script = data.get("joinScript")

                if not join_script:
                    return None

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
# TRACKER
# =========================================================

@tasks.loop(seconds=CHECK_INTERVAL)
async def server_tracker():

    global server_database

    current_time = int(time.time())

    print(f"[{datetime.utcnow()}] Scanning servers...")

    servers = await fetch_servers()

    if not servers:
        print("No servers fetched.")
        return

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
                print(
                    f"[SKIPPED] {server_id} "
                    f"(no claimed time)"
                )
                continue

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

            await asyncio.sleep(0.5)

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

            target_time = spawn_time - ANNOUNCE_EARLY

            if (
                target_time <= uptime <
                target_time + CHECK_INTERVAL
                and spawn_time not in
                server_database[server_id]["rift_sent"]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"🌀 **Rift spawning in 5 minutes**\n\n"
                        f"⏱️ Current Server Age:\n"
                        f"`{format_time(uptime)}`\n\n"
                        f"🎯 Rift Spawn Time:\n"
                        f"`{format_time(spawn_time)}`\n\n"
                        f"🆔 `{server_id}`\n\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "rift_sent"
                ].append(spawn_time)

                print(
                    f"[RIFT] {server_id} "
                    f"{format_time(spawn_time)}"
                )

        # =================================================
        # BOSS ALERTS
        # =================================================

        for spawn_time in BOSS_TIMES:

            target_time = spawn_time - ANNOUNCE_EARLY

            if (
                target_time <= uptime <
                target_time + CHECK_INTERVAL
                and spawn_time not in
                server_database[server_id]["boss_sent"]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"👹 **Boss spawning in 5 minutes**\n\n"
                        f"⏱️ Current Server Age:\n"
                        f"`{format_time(uptime)}`\n\n"
                        f"🎯 Boss Spawn Time:\n"
                        f"`{format_time(spawn_time)}`\n\n"
                        f"🆔 `{server_id}`\n\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "boss_sent"
                ].append(spawn_time)

                print(
                    f"[BOSS] {server_id} "
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
                > CHECK_INTERVAL * 4
            ):

                dead_servers.append(server_id)

        else:

            uptime = (
                current_time
                - data["claimed_time"]
            )

            if uptime > MAX_SERVER_AGE:
                dead_servers.append(server_id)

    for dead in dead_servers:

        if dead in server_database:

            print(f"[REMOVED] {dead}")

            del server_database[dead]

    save_data()

    print(
        f"Tracking {len(server_database)} servers"
    )

# =========================================================
# COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Bot status"
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

    await interaction.response.defer()

    if server_id not in server_database:

        await interaction.followup.send(
            "❌ Server not tracked."
        )

        return

    uptime_seconds = (
        int(time.time())
        - server_database[server_id][
            "claimed_time"
        ]
    )

    await interaction.followup.send(
        f"⏱️ Uptime:\n"
        f"`{format_time(uptime_seconds)}`"
    )

# =========================================================
# READY
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

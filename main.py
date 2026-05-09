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
    return "Tracker Online"

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

MAX_SERVER_AGE = 172800

EARLY_WARNING = 300

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
# SERVER API
# =========================================================

BASE_URL = (
    f"https://games.roblox.com/v1/games/"
    f"{PLACE_ID}/servers/Public?limit=100"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

async def fetch_servers():

    servers = []
    cursor = None

    async with aiohttp.ClientSession(
        headers=HEADERS
    ) as session:

        while True:

            url = BASE_URL

            if cursor:
                url += f"&cursor={cursor}"

            try:

                async with session.get(url) as response:

                    if response.status == 429:

                        print("RATE LIMITED")
                        await asyncio.sleep(15)
                        break

                    if response.status != 200:

                        print(
                            f"API Error: "
                            f"{response.status}"
                        )

                        break

                    data = await response.json()

                    batch = data.get("data", [])

                    servers.extend(batch)

                    cursor = data.get(
                        "nextPageCursor"
                    )

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

    url = (
        "https://gamejoin.roblox.com/"
        "v1/join-game-instance"
    )

    payload = {
        "placeId": PLACE_ID,
        "gameId": server_id,
        "gameJoinAttemptId": server_id
    }

    headers = {
        "Content-Type": "application/json",
        "Referer": (
            f"https://www.roblox.com/games/"
            f"{PLACE_ID}/"
        ),
        "Origin": "https://www.roblox.com",
        "User-Agent": "Mozilla/5.0"
    }

    cookies = {
        ".ROBLOSECURITY": ROBLOX_COOKIE
    }

    try:

        async with aiohttp.ClientSession(
            headers=headers,
            cookies=cookies
        ) as session:

            async with session.post(
                url,
                json=payload
            ) as response:

                if response.status == 429:

                    print(
                        f"CLAIMED TIME "
                        f"RATE LIMITED"
                    )

                    return None

                if response.status != 200:

                    print(
                        f"Claimed Time Error: "
                        f"{response.status}"
                    )

                    return None

                data = await response.json()

                join_script = data.get(
                    "joinScript"
                )

                if not join_script:
                    return None

                claimed_time = join_script.get(
                    "ServerClaimedTime"
                )

                if not claimed_time:
                    return None

                return int(
                    claimed_time / 1000
                )

    except Exception as e:

        print("Claimed Error:", e)

    return None

# =========================================================
# FORMAT TIME
# =========================================================

def format_time(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    return (
        f"{hours}h "
        f"{minutes}m "
        f"{seconds}s"
    )

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

    print(
        f"\n[{datetime.utcnow()}] "
        f"Scanning..."
    )

    servers = await fetch_servers()

    print(
        f"Found {len(servers)} servers"
    )

    live_servers = set()

    for server in servers:

        server_id = server["id"]

        live_servers.add(server_id)

        # =================================================
        # NEW SERVER
        # =================================================

        if server_id not in server_database:

            print(
                f"Fetching uptime for "
                f"{server_id}"
            )

            claimed_time = (
                await get_server_claimed_time(
                    server_id
                )
            )

            if not claimed_time:

                print(
                    f"Failed uptime "
                    f"{server_id}"
                )

                continue

            server_database[server_id] = {
                "claimed_time": claimed_time,
                "last_seen": current_time,
                "rift_sent": [],
                "boss_sent": []
            }

            uptime = (
                current_time
                - claimed_time
            )

            print(
                f"NEW SERVER "
                f"{server_id} | "
                f"{format_time(uptime)}"
            )

            save_data()

            await asyncio.sleep(1)

        else:

            server_database[server_id][
                "last_seen"
            ] = current_time

        # =================================================
        # UPTIME
        # =================================================

        claimed_time = (
            server_database[server_id][
                "claimed_time"
            ]
        )

        uptime = (
            current_time
            - claimed_time
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

            warning_time = (
                spawn_time
                - EARLY_WARNING
            )

            if (
                warning_time
                <= uptime
                <= warning_time + CHECK_INTERVAL
            ):

                if (
                    spawn_time not in
                    server_database[server_id][
                        "rift_sent"
                    ]
                ):

                    channel = bot.get_channel(
                        RIFT_CHANNEL_ID
                    )

                    if channel:

                        await channel.send(
                            f"🌀 **RIFT IN 5 MINUTES**\n\n"
                            f"⏱️ Server Age:\n"
                            f"`{format_time(uptime)}`\n\n"
                            f"🎯 Rift Spawn:\n"
                            f"`{format_time(spawn_time)}`\n\n"
                            f"🆔 `{server_id}`\n\n"
                            f"🔗 {join_link}"
                        )

                        print(
                            f"RIFT SENT "
                            f"{server_id}"
                        )

                    server_database[
                        server_id
                    ][
                        "rift_sent"
                    ].append(spawn_time)

        # =================================================
        # BOSS ALERTS
        # =================================================

        for spawn_time in BOSS_TIMES:

            warning_time = (
                spawn_time
                - EARLY_WARNING
            )

            if (
                warning_time
                <= uptime
                <= warning_time + CHECK_INTERVAL
            ):

                if (
                    spawn_time not in
                    server_database[server_id][
                        "boss_sent"
                    ]
                ):

                    channel = bot.get_channel(
                        BOSS_CHANNEL_ID
                    )

                    if channel:

                        await channel.send(
                            f"👹 **BOSS IN 5 MINUTES**\n\n"
                            f"⏱️ Server Age:\n"
                            f"`{format_time(uptime)}`\n\n"
                            f"🎯 Boss Spawn:\n"
                            f"`{format_time(spawn_time)}`\n\n"
                            f"🆔 `{server_id}`\n\n"
                            f"🔗 {join_link}"
                        )

                        print(
                            f"BOSS SENT "
                            f"{server_id}"
                        )

                    server_database[
                        server_id
                    ][
                        "boss_sent"
                    ].append(spawn_time)

    # =====================================================
    # CLEANUP
    # =====================================================

    dead_servers = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if (
                current_time
                - data["last_seen"]
                > 1800
            ):

                dead_servers.append(
                    server_id
                )

    for server_id in dead_servers:

        del server_database[server_id]

        print(
            f"REMOVED {server_id}"
        )

    save_data()

    print(
        f"Tracking "
        f"{len(server_database)} servers"
    )

# =========================================================
# COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Ping"
)
async def ping(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "🏓 Pong!"
    )

@bot.tree.command(
    name="tracked",
    description="Tracked servers"
)
async def tracked(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        f"Tracking "
        f"{len(server_database)} servers"
    )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    try:

        synced = await bot.tree.sync()

        print(
            f"Synced "
            f"{len(synced)} commands"
        )

    except Exception as e:

        print("Sync Error:", e)

    if not server_tracker.is_running():

        server_tracker.start()

# =========================================================
# START
# =========================================================

threading.Thread(
    target=run_web
).start()

bot.run(TOKEN)

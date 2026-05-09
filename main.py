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
MAX_SERVER_AGE = 172800

DATA_FILE = "servers.json"

RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

# 5 minutes before spawn
ALERT_BEFORE = 300

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
# FORMAT TIME
# =========================================================

def format_time(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    return f"{hours}h {minutes}m {seconds}s"

# =========================================================
# ROBLOX SERVERS
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

                        print("Rate limited. Sleeping...")

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

                    await asyncio.sleep(0.5)

            except Exception as e:

                print("Fetch Error:", e)
                break

    return servers

# =========================================================
# GET REAL CLAIMED TIME
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
                        f"Claimed Time Failed "
                        f"{server_id} "
                        f"{response.status}"
                    )

                    return None

                data = await response.json()

                join_script = data.get("joinScript")

                if not join_script:
                    return None

                claimed_time = join_script.get(
                    "ServerClaimedTime"
                )

                if not claimed_time:
                    return None

                claimed_time = int(claimed_time / 1000)

                print(
                    f"[CLAIMED TIME] "
                    f"{server_id} -> {claimed_time}"
                )

                return claimed_time

    except Exception as e:

        print("Claimed Time Error:", e)

    return None

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
async def tracker():

    global server_database

    current_time = int(time.time())

    print(f"\n[{datetime.utcnow()}] SCANNING")

    servers = await fetch_servers()

    if not servers:

        print("No servers found")
        return

    live_servers = set()

    for server in servers:

        server_id = server["id"]

        live_servers.add(server_id)

        # =================================================
        # NEW SERVER
        # =================================================

        if server_id not in server_database:

            print(f"[NEW SERVER] {server_id}")

            claimed_time = await get_server_claimed_time(
                server_id
            )

            if not claimed_time:

                print(
                    f"[FAILED CLAIMED TIME] "
                    f"{server_id}"
                )

                continue

            server_database[server_id] = {

                "claimed_time": claimed_time,
                "last_seen": current_time,

                "rift_sent": [],
                "boss_sent": []

            }

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

        print(
            f"{server_id} -> "
            f"{format_time(uptime)}"
        )

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
                0 <= remaining <= ALERT_BEFORE
                and spawn_time not in
                server_database[server_id]["rift_sent"]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"🌀 **Rift Soon**\n\n"
                        f"⏳ Spawns in "
                        f"`{format_time(remaining)}`\n"
                        f"🕒 Server Age "
                        f"`{format_time(uptime)}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "rift_sent"
                ].append(spawn_time)

                print(
                    f"[RIFT ALERT] {server_id}"
                )

        # =================================================
        # BOSS ALERTS
        # =================================================

        for spawn_time in BOSS_TIMES:

            remaining = spawn_time - uptime

            if (
                0 <= remaining <= ALERT_BEFORE
                and spawn_time not in
                server_database[server_id]["boss_sent"]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    await channel.send(
                        f"👹 **Boss Soon**\n\n"
                        f"⏳ Spawns in "
                        f"`{format_time(remaining)}`\n"
                        f"🕒 Server Age "
                        f"`{format_time(uptime)}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "boss_sent"
                ].append(spawn_time)

                print(
                    f"[BOSS ALERT] {server_id}"
                )

    # =====================================================
    # CLEANUP
    # =====================================================

    dead_servers = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if (
                current_time - data["last_seen"]
                > 300
            ):

                dead_servers.append(server_id)

    for dead in dead_servers:

        del server_database[dead]

        print(f"[REMOVED] {dead}")

    save_data()

    print(
        f"Tracking "
        f"{len(server_database)} servers"
    )

# =========================================================
# COMMANDS
# =========================================================

@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(
        "Pong!"
    )

@bot.tree.command(name="tracked")
async def tracked(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Tracking {len(server_database)} servers"
    )

@bot.tree.command(name="uptime")
async def uptime(
    interaction: discord.Interaction,
    server_id: str
):

    await interaction.response.defer()

    if server_id not in server_database:

        await interaction.followup.send(
            "Server not tracked"
        )

        return

    uptime_seconds = (
        int(time.time())
        - server_database[server_id][
            "claimed_time"
        ]
    )

    await interaction.followup.send(
        f"Uptime: "
        f"{format_time(uptime_seconds)}"
    )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    try:
        await bot.tree.sync()
    except Exception as e:
        print("Slash Sync Error:", e)

    if not tracker.is_running():
        tracker.start()

# =========================================================
# START
# =========================================================

threading.Thread(
    target=run_web,
    daemon=True
).start()

bot.run(TOKEN)

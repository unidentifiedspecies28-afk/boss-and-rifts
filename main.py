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
CHECK_INTERVAL = 20

DATA_FILE = "servers.json"

RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

MAX_SERVER_AGE = 172800

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
# ROBLOX URLS
# =========================================================

BASE_URL = (
    f"https://games.roblox.com/v1/games/"
    f"{PLACE_ID}/servers/Public?limit=100"
)

JOIN_URL = (
    "https://gamejoin.roblox.com/v1/join-game-instance"
)

# =========================================================
# FETCH SERVERS
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

            except:
                break

    return servers

# =========================================================
# GET REAL UPTIME
# =========================================================

async def fetch_real_uptime(server_id):

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

    valid_results = []

    # =====================================================
    # MULTIPLE CHECKS
    # =====================================================

    for _ in range(3):

        try:

            async with aiohttp.ClientSession() as session:

                async with session.post(
                    JOIN_URL,
                    headers=headers,
                    json=payload
                ) as response:

                    if response.status != 200:
                        continue

                    data = await response.json()

                    returned_job_id = data.get(
                        "jobId"
                    )

                    # Reject redirects
                    if returned_job_id != server_id:
                        continue

                    join_script = data.get(
                        "joinScript",
                        {}
                    )

                    claimed_time = join_script.get(
                        "ServerClaimedTime"
                    )

                    if not claimed_time:
                        continue

                    current_ms = int(
                        time.time() * 1000
                    )

                    uptime = (
                        current_ms - claimed_time
                    ) // 1000

                    # Reject impossible values
                    if uptime < 0:
                        continue

                    if uptime > MAX_SERVER_AGE:
                        continue

                    valid_results.append(
                        int(uptime)
                    )

        except:
            pass

        await asyncio.sleep(0.4)

    # =====================================================
    # NO VALID RESULTS
    # =====================================================

    if not valid_results:
        return None

    # =====================================================
    # USE MEDIAN RESULT
    # =====================================================

    valid_results.sort()

    median = valid_results[
        len(valid_results) // 2
    ]

    return median

# =========================================================
# FORMAT TIME
# =========================================================

def format_time(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    return f"{hours}h {minutes}m"

# =========================================================
# EVENT SETTINGS
# =========================================================

RIFT_INTERVAL = 5400
RIFT_WARNING = 300

BOSS_INTERVAL = 7200
BOSS_WARNING = 300

# =========================================================
# TRACKER
# =========================================================

@tasks.loop(seconds=CHECK_INTERVAL)
async def server_tracker():

    current_time = int(time.time())

    print(
        f"[{datetime.utcnow()}] Scanning..."
    )

    servers = await fetch_servers()

    live_server_ids = set()

    for server in servers:

        server_id = server["id"]

        live_server_ids.add(server_id)

        # =================================================
        # CREATE ENTRY
        # =================================================

        if server_id not in server_database:

            real_uptime = await fetch_real_uptime(
                server_id
            )

            if real_uptime is None:
                continue

            server_database[server_id] = {

                "uptime": real_uptime,

                "last_check": current_time,

                "rift_sent": [],

                "boss_sent": [],

                "last_seen": current_time
            }

            print(
                f"[NEW] {server_id}"
            )

else:

    data = server_database[server_id]

    elapsed = (
        current_time
        - data["last_check"]
    )

    predicted_uptime = (
        data["uptime"] + elapsed
    )

    data["last_check"] = current_time

    # =================================================
    # FETCH VERIFIED UPTIME
    # =================================================

    real_uptime = await fetch_real_uptime(
        server_id
    )

    if real_uptime is not None:

        difference = abs(
            real_uptime
            - predicted_uptime
        )

        # =============================================
        # ACCEPT SMALL DIFFERENCES
        # =============================================

        if difference <= 120:

            data["uptime"] = real_uptime

        # =============================================
        # MEDIUM DIFFERENCE:
        # SMOOTH CORRECTION
        # =============================================

        elif difference <= 600:

            averaged = int(
                (
                    predicted_uptime
                    + real_uptime
                ) / 2
            )

            data["uptime"] = averaged

        # =============================================
        # MASSIVE DIFFERENCE:
        # IGNORE ROBLOX RESPONSE
        # =============================================

        else:

            data["uptime"] = predicted_uptime

            print(
                f"[IGNORED BAD UPTIME] "
                f"{server_id}"
            )

    else:

        data["uptime"] = predicted_uptime

    data["last_seen"] = current_time

        uptime = server_database[server_id]["uptime"]

        join_link = (
            f"https://www.roblox.com/games/start?"
            f"placeId={PLACE_ID}"
            f"&gameInstanceId={server_id}"
        )

        # =================================================
        # RIFTS
        # =================================================

        next_rift = (
            (
                uptime // RIFT_INTERVAL
            ) + 1
        ) * RIFT_INTERVAL

        rift_warning_time = (
            next_rift - RIFT_WARNING
        )

        if (
            uptime >= rift_warning_time
            and uptime < next_rift
        ):

            if (
                next_rift
                not in server_database[server_id]["rift_sent"]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    remaining = (
                        next_rift - uptime
                    )

                    await channel.send(
                        f"🌀 **Rift Spawning Soon**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"⚠️ Rift In: "
                        f"`{format_time(remaining)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id]["rift_sent"].append(
                    next_rift
                )

        # =================================================
        # BOSSES
        # =================================================

        next_boss = (
            (
                uptime // BOSS_INTERVAL
            ) + 1
        ) * BOSS_INTERVAL

        boss_warning_time = (
            next_boss - BOSS_WARNING
        )

        if (
            uptime >= boss_warning_time
            and uptime < next_boss
        ):

            if (
                next_boss
                not in server_database[server_id]["boss_sent"]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    remaining = (
                        next_boss - uptime
                    )

                    await channel.send(
                        f"👹 **Boss Spawning Soon**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"⚠️ Boss In: "
                        f"`{format_time(remaining)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id]["boss_sent"].append(
                    next_boss
                )

    # =====================================================
    # REMOVE DEAD SERVERS
    # =====================================================

    remove_list = []

    for saved_server_id in server_database:

        if saved_server_id not in live_server_ids:

            last_seen = server_database[
                saved_server_id
            ]["last_seen"]

            if (
                current_time - last_seen
            ) > (CHECK_INTERVAL * 2):

                remove_list.append(
                    saved_server_id
                )

    for dead in remove_list:

        print(f"[REMOVED] {dead}")

        del server_database[dead]

    save_data()

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check bot status"
)
async def ping(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "🏓 Pong!"
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

threading.Thread(
    target=run_web
).start()

bot.run(TOKEN)

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

    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        while True:

            url = BASE_URL

            if cursor:
                url += f"&cursor={cursor}"

            try:

                async with session.get(url) as response:

                    if response.status == 429:

                        print(
                            "[RATE LIMITED] Waiting..."
                        )

                        await asyncio.sleep(5)
                        continue

                    if response.status != 200:

                        print(
                            f"[SERVER API ERROR] "
                            f"{response.status}"
                        )

                        break

                    data = await response.json()

                    batch = data.get("data", [])

                    servers.extend(batch)

                    print(
                        f"[FETCHED] "
                        f"{len(batch)} servers"
                    )

                    cursor = data.get(
                        "nextPageCursor"
                    )

                    if not cursor:
                        break

                    await asyncio.sleep(0.2)

            except Exception as e:

                print(
                    f"[FETCH ERROR] {e}"
                )

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

    timeout = aiohttp.ClientTimeout(total=15)

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                JOIN_URL,
                headers=headers,
                json=payload
            ) as response:

                if response.status == 429:

                    print(
                        f"[429 JOIN API] {server_id}"
                    )

                    return None

                if response.status != 200:

                    print(
                        f"[JOIN ERROR] "
                        f"{server_id} "
                        f"-> {response.status}"
                    )

                    return None

                data = await response.json()

                returned_job_id = data.get(
                    "jobId"
                )

                if returned_job_id != server_id:

                    print(
                        f"[WRONG SERVER RETURNED]\n"
                        f"Requested: {server_id}\n"
                        f"Returned:  {returned_job_id}"
                    )

                    return None

                join_script = data.get(
                    "joinScript",
                    {}
                )

                claimed_time = join_script.get(
                    "ServerClaimedTime"
                )

                if not claimed_time:

                    print(
                        f"[NO CLAIMED TIME] "
                        f"{server_id}"
                    )

                    return None

                current_ms = int(
                    time.time() * 1000
                )

                uptime = (
                    current_ms - claimed_time
                ) // 1000

                if uptime < 0:

                    print(
                        f"[NEGATIVE UPTIME] "
                        f"{server_id}"
                    )

                    return None

                if uptime > MAX_SERVER_AGE:

                    print(
                        f"[UPTIME TOO HIGH] "
                        f"{server_id}"
                    )

                    return None

                print(
                    f"[UPTIME OK] "
                    f"{server_id} "
                    f"-> {uptime}s"
                )

                return int(uptime)

    except Exception as e:

        print(
            f"[UPTIME ERROR] "
            f"{server_id} -> {e}"
        )

        return None

# =========================================================
# FORMAT TIME
# =========================================================

def format_time(seconds):

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    return f"{hours}h {minutes}m {secs}s"

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
        f"\n[{datetime.utcnow()}] "
        f"Starting scan..."
    )

    servers = await fetch_servers()

    print(
        f"[TOTAL SERVERS FOUND] "
        f"{len(servers)}"
    )

    live_server_ids = set()

    for index, server in enumerate(servers):

        server_id = server["id"]

        print(
            f"[{index + 1}/{len(servers)}] "
            f"Checking {server_id}"
        )

        live_server_ids.add(server_id)

        # =================================================
        # NEW SERVER
        # =================================================

        if server_id not in server_database:

            uptime = await fetch_real_uptime(
                server_id
            )

            if uptime is None:

                print(
                    f"[SKIPPED] "
                    f"{server_id}"
                )

                continue

            server_database[server_id] = {

                "uptime": uptime,

                "last_sync": current_time,

                "rift_sent": [],

                "boss_sent": [],

                "last_seen": current_time
            }

            print(
                f"[TRACKING NEW] "
                f"{server_id} "
                f"({format_time(uptime)})"
            )

        else:

            data = server_database[server_id]

            # =================================================
            # ALWAYS RESYNC REAL UPTIME
            # =================================================

            real_uptime = await fetch_real_uptime(
                server_id
            )

            if real_uptime is not None:

                old_uptime = data["uptime"]

                data["uptime"] = real_uptime

                print(
                    f"[SYNCED] "
                    f"{server_id} "
                    f"{old_uptime}s -> "
                    f"{real_uptime}s"
                )

            else:

                elapsed = (
                    current_time
                    - data["last_sync"]
                )

                data["uptime"] += elapsed

                print(
                    f"[FALLBACK TIMER] "
                    f"{server_id} "
                    f"-> "
                    f"{data['uptime']}s"
                )

            data["last_sync"] = current_time
            data["last_seen"] = current_time

        uptime = server_database[server_id]["uptime"]

        # =================================================
        # JOIN LINK
        # =================================================

        join_link = (
            f"https://unidentifiedspecies28-afk.github.io/"
            f"boss-and-rifts/?jobId={server_id}"
        )

        # =================================================
        # RIFT WARNINGS
        # =================================================

        next_rift = (
            (
                uptime // RIFT_INTERVAL
            ) + 1
        ) * RIFT_INTERVAL

        remaining_rift = (
            next_rift - uptime
        )

        if (
            0 < remaining_rift <= RIFT_WARNING
        ):

            if (
                next_rift
                not in server_database[server_id]["rift_sent"]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    print(
                        f"[SENDING RIFT] "
                        f"{server_id}"
                    )

                    await channel.send(
                        f"🌀 **Rift Spawning Soon**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"⚠️ Rift In: "
                        f"`{format_time(remaining_rift)}`\n"
                        f"🎯 Rift At: "
                        f"`{format_time(next_rift)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 [Join Server]({join_link})"
                    )

                server_database[server_id][
                    "rift_sent"
                ].append(next_rift)

        # =================================================
        # BOSS WARNINGS
        # =================================================

        next_boss = (
            (
                uptime // BOSS_INTERVAL
            ) + 1
        ) * BOSS_INTERVAL

        remaining_boss = (
            next_boss - uptime
        )

        if (
            0 < remaining_boss <= BOSS_WARNING
        ):

            if (
                next_boss
                not in server_database[server_id]["boss_sent"]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    print(
                        f"[SENDING BOSS] "
                        f"{server_id}"
                    )

                    await channel.send(
                        f"👹 **Boss Spawning Soon**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"⚠️ Boss In: "
                        f"`{format_time(remaining_boss)}`\n"
                        f"🎯 Boss At: "
                        f"`{format_time(next_boss)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 [Join Server]({join_link})"
                    )

                server_database[server_id][
                    "boss_sent"
                ].append(next_boss)

    # =====================================================
    # REMOVE DEAD SERVERS
    # =====================================================

    remove_list = []

    for saved_server_id in list(server_database.keys()):

        if saved_server_id not in live_server_ids:

            last_seen = server_database[
                saved_server_id
            ]["last_seen"]

            if (
                current_time - last_seen
            ) > (CHECK_INTERVAL * 3):

                remove_list.append(
                    saved_server_id
                )

    for dead in remove_list:

        print(
            f"[REMOVED DEAD SERVER] "
            f"{dead}"
        )

        del server_database[dead]

    save_data()

    print(
        f"[SCAN COMPLETE] "
        f"Tracking "
        f"{len(server_database)} servers"
    )

# =========================================================
# COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Bot status"
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
        f"`{len(server_database)}` "
        f"servers."
    )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user}"
    )

    try:

        synced = await bot.tree.sync()

        print(
            f"Synced "
            f"{len(synced)} commands"
        )

    except Exception as e:

        print(
            f"[SYNC ERROR] {e}"
        )

    if not server_tracker.is_running():

        print(
            "[TRACKER STARTED]"
        )

        server_tracker.start()

# =========================================================
# START
# =========================================================

threading.Thread(
    target=run_web,
    daemon=True
).start()

bot.run(TOKEN)

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

CHECK_INTERVAL = 15
DATA_FILE = "servers.json"

RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

MAX_SERVER_AGE = 172800

# =========================================================
# EVENT SETTINGS
# =========================================================

RIFT_INTERVAL = 5400
RIFT_WARNING = 300

BOSS_INTERVAL = 7200
BOSS_WARNING = 300

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
# URLS
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

    timeout = aiohttp.ClientTimeout(total=20)

    headers = {
        "User-Agent": "Roblox/WinInet"
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers
    ) as session:

        while True:

            url = BASE_URL

            if cursor:
                url += f"&cursor={cursor}"

            try:

                async with session.get(url) as response:

                    if response.status == 429:

                        print("[RATE LIMITED]")
                        await asyncio.sleep(5)
                        break

                    if response.status != 200:

                        print(
                            f"[SERVER LIST ERROR] "
                            f"{response.status}"
                        )
                        break

                    data = await response.json()

                    page_servers = data.get(
                        "data",
                        []
                    )

                    servers.extend(page_servers)

                    print(
                        f"[PAGE] "
                        f"Fetched {len(page_servers)} servers"
                    )

                    cursor = data.get(
                        "nextPageCursor"
                    )

                    if not cursor:
                        break

                    await asyncio.sleep(0.25)

            except Exception as e:

                print(
                    f"[FETCH ERROR] {e}"
                )
                break

    print(
        f"[TOTAL SERVERS] {len(servers)}"
    )

    return servers

# =========================================================
# GET REAL SERVER UPTIME
# =========================================================

async def fetch_real_uptime(
    session,
    server_id
):

    headers = {
        "Cookie": (
            f".ROBLOSECURITY={ROBLOX_COOKIE}"
        ),
        "Content-Type": "application/json",
        "User-Agent": "Roblox/WinInet",
        "Referer": (
            f"https://www.roblox.com/games/"
            f"{PLACE_ID}/"
        )
    }

    payload = {
        "placeId": PLACE_ID,
        "gameId": server_id,
        "gameJoinAttemptId": str(uuid.uuid4())
    }

    try:

        async with session.post(
            JOIN_URL,
            headers=headers,
            json=payload
        ) as response:

            if response.status == 429:

                print(
                    f"[429] {server_id}"
                )

                return None

            if response.status != 200:

                print(
                    f"[JOIN ERROR] "
                    f"{server_id} "
                    f"{response.status}"
                )

                return None

            data = await response.json()

            returned_job_id = data.get(
                "jobId"
            )

            if returned_job_id != server_id:

                print(
                    f"[MISMATCH] "
                    f"{server_id}"
                )

                return None

            join_script = data.get(
                "joinScript"
            )

            if not join_script:

                print(
                    f"[NO JOIN SCRIPT] "
                    f"{server_id}"
                )

                return None

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

            uptime = int(
                (current_ms - claimed_time)
                / 1000
            )

            if uptime < 0:

                print(
                    f"[NEGATIVE UPTIME] "
                    f"{server_id}"
                )

                return None

            if uptime > MAX_SERVER_AGE:

                print(
                    f"[TOO OLD] "
                    f"{server_id}"
                )

                return None

            print(
                f"[UPTIME] "
                f"{server_id} "
                f"{uptime}s"
            )

            return uptime

    except Exception as e:

        print(
            f"[UPTIME ERROR] "
            f"{server_id} "
            f"{e}"
        )

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
# TRACKER
# =========================================================

@tasks.loop(seconds=CHECK_INTERVAL)
async def server_tracker():

    current_time = int(time.time())

    print(
        f"\n[{datetime.utcnow()}] "
        f"SCANNING SERVERS"
    )

    servers = await fetch_servers()

    live_servers = set()

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        for server in servers:

            try:

                server_id = server["id"]

                live_servers.add(server_id)

                print(
                    f"[CHECKING] "
                    f"{server_id}"
                )

                # =====================================
                # GET REAL UPTIME EVERY SCAN
                # =====================================

                real_uptime = await fetch_real_uptime(
                    session,
                    server_id
                )

                if real_uptime is None:

                    print(
                        f"[SKIPPED] "
                        f"{server_id}"
                    )

                    continue

                # =====================================
                # CREATE DATABASE ENTRY
                # =====================================

                if server_id not in server_database:

                    server_database[server_id] = {

                        "rift_sent": [],

                        "boss_sent": [],

                        "last_seen": current_time
                    }

                    print(
                        f"[NEW SERVER] "
                        f"{server_id}"
                    )

                server_database[server_id][
                    "last_seen"
                ] = current_time

                uptime = real_uptime

                # =====================================
                # JOIN LINK
                # =====================================

                join_link = (
                    f"https://unidentifiedspecies28-afk.github.io/"
                    f"boss-and-rifts/?jobId={server_id}"
                )

                # =====================================
                # RIFTS
                # =====================================

                next_rift = (
                    (
                        uptime // RIFT_INTERVAL
                    ) + 1
                ) * RIFT_INTERVAL

                time_until_rift = (
                    next_rift - uptime
                )

                print(
                    f"[RIFT TIMER] "
                    f"{server_id} "
                    f"{time_until_rift}s"
                )

                if (
                    0
                    <= time_until_rift
                    <= RIFT_WARNING
                ):

                    if (
                        next_rift
                        not in server_database[
                            server_id
                        ]["rift_sent"]
                    ):

                        channel = bot.get_channel(
                            RIFT_CHANNEL_ID
                        )

                        if channel:

                            await channel.send(
                                f"🌀 **Rift Spawning Soon**\n\n"
                                f"⏱️ Server Age: "
                                f"`{format_time(uptime)}`\n"
                                f"⚠️ Rift In: "
                                f"`{format_time(time_until_rift)}`\n"
                                f"🆔 `{server_id}`\n"
                                f"🔗 [Join Server]({join_link})"
                            )

                            print(
                                f"[RIFT SENT] "
                                f"{server_id}"
                            )

                        server_database[
                            server_id
                        ]["rift_sent"].append(
                            next_rift
                        )

                # =====================================
                # BOSSES
                # =====================================

                next_boss = (
                    (
                        uptime // BOSS_INTERVAL
                    ) + 1
                ) * BOSS_INTERVAL

                time_until_boss = (
                    next_boss - uptime
                )

                print(
                    f"[BOSS TIMER] "
                    f"{server_id} "
                    f"{time_until_boss}s"
                )

                if (
                    0
                    <= time_until_boss
                    <= BOSS_WARNING
                ):

                    if (
                        next_boss
                        not in server_database[
                            server_id
                        ]["boss_sent"]
                    ):

                        channel = bot.get_channel(
                            BOSS_CHANNEL_ID
                        )

                        if channel:

                            await channel.send(
                                f"👹 **Boss Spawning Soon**\n\n"
                                f"⏱️ Server Age: "
                                f"`{format_time(uptime)}`\n"
                                f"⚠️ Boss In: "
                                f"`{format_time(time_until_boss)}`\n"
                                f"🆔 `{server_id}`\n"
                                f"🔗 [Join Server]({join_link})"
                            )

                            print(
                                f"[BOSS SENT] "
                                f"{server_id}"
                            )

                        server_database[
                            server_id
                        ]["boss_sent"].append(
                            next_boss
                        )

                await asyncio.sleep(0.4)

            except Exception as e:

                print(
                    f"[TRACK ERROR] {e}"
                )

    # =====================================================
    # REMOVE DEAD SERVERS
    # =====================================================

    dead_servers = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if (
                current_time
                - data["last_seen"]
            ) > 90:

                dead_servers.append(
                    server_id
                )

    for dead in dead_servers:

        print(
            f"[REMOVED] {dead}"
        )

        del server_database[dead]

    save_data()

    print(
        f"[TRACKING] "
        f"{len(server_database)} servers"
    )

# =========================================================
# COMMANDS
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

@bot.tree.command(
    name="tracked",
    description="Tracked server count"
)
async def tracked(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        f"Tracking "
        f"`{len(server_database)}` servers."
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

        server_tracker.start()

# =========================================================
# START
# =========================================================

threading.Thread(
    target=run_web
).start()

bot.run(TOKEN)

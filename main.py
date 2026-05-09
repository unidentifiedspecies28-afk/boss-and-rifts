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

PLACE_ID = 13358463560
CHECK_INTERVAL = 20
DATA_FILE = "servers.json"

# CHANGE THESE
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
# IGNORE EXISTING SERVERS ON STARTUP
# =========================================================

FIRST_SCAN_COMPLETE = False

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

    ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE")

    headers = {}

    # Use authenticated Roblox session if provided
    if ROBLOX_COOKIE:

        headers["Cookie"] = (
            f".ROBLOSECURITY={ROBLOX_COOKIE}"
        )

    async with aiohttp.ClientSession(
        headers=headers
    ) as session:

        while True:

            url = BASE_URL

            if cursor:
                url += f"&cursor={cursor}"

            try:

                async with session.get(url) as response:

                    if response.status != 200:

                        print(
                            f"API Error: {response.status}"
                        )

                        text = await response.text()

                        print(text)

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

    global server_database
    global FIRST_SCAN_COMPLETE

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

            server_database[server_id] = {
                "first_seen": current_time,
                "last_seen": current_time,
                "rift_announced": [],
                "boss_announced": []
            }

            # Ignore startup servers
            if FIRST_SCAN_COMPLETE:
                print(f"[NEW SERVER] {server_id}")

        else:

            server_database[server_id]["last_seen"] = current_time

        # =================================================
        # SKIP INITIAL SERVERS
        # =================================================

        if not FIRST_SCAN_COMPLETE:
            continue

        # =================================================
        # UPTIME
        # =================================================

        uptime = (
            current_time
            - server_database[server_id]["first_seen"]
        )

        join_link = (
            f"https://www.roblox.com/games/start?"
            f"placeId={PLACE_ID}"
            f"&gameInstanceId={server_id}"
        )

        # =================================================
        # RIFT ANNOUNCEMENTS
        # =================================================

        for milestone in RIFT_MILESTONES:

            if (
                uptime >= milestone
                and milestone not in server_database[server_id]["rift_announced"]
            ):

                channel = bot.get_channel(RIFT_CHANNEL_ID)

                if channel:

                    await channel.send(
                        f"🌀 **Rift Server Found**\n\n"
                        f"⏱️ Uptime: `{format_time(milestone)}`\n"
                        f"🆔 Server ID: `{server_id}`\n"
                        f"🔗 Join:\n{join_link}"
                    )

                server_database[server_id]["rift_announced"].append(milestone)

                print(
                    f"[RIFT] {server_id} "
                    f"{format_time(milestone)}"
                )

        # =================================================
        # BOSS ANNOUNCEMENTS
        # =================================================

        for milestone in BOSS_MILESTONES:

            if (
                uptime >= milestone
                and milestone not in server_database[server_id]["boss_announced"]
            ):

                channel = bot.get_channel(BOSS_CHANNEL_ID)

                if channel:

                    await channel.send(
                        f"👹 **Boss Server Found**\n\n"
                        f"⏱️ Uptime: `{format_time(milestone)}`\n"
                        f"🆔 Server ID: `{server_id}`\n"
                        f"🔗 Join:\n{join_link}"
                    )

                server_database[server_id]["boss_announced"].append(milestone)

                print(
                    f"[BOSS] {server_id} "
                    f"{format_time(milestone)}"
                )

    # =====================================================
    # REMOVE DEAD SERVERS
    # =====================================================

    dead_servers = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if current_time - data["last_seen"] > CHECK_INTERVAL * 2:

                uptime = (
                    data["last_seen"]
                    - data["first_seen"]
                )

                print(
                    f"[CLOSED] {server_id} "
                    f"after {format_time(uptime)}"
                )

                dead_servers.append(server_id)

    for dead in dead_servers:
        del server_database[dead]

    save_data()

    # =====================================================
    # FIRST SCAN COMPLETE
    # =====================================================

    if not FIRST_SCAN_COMPLETE:
        FIRST_SCAN_COMPLETE = True
        print("Initial scan complete.")

    print(f"Tracking {len(live_servers)} live servers")

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check if the bot is online"
)
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message("🏓 Pong!")

@bot.tree.command(
    name="tracked",
    description="Show tracked server count"
)
async def tracked(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Tracking `{len(server_database)}` servers."
    )

@bot.tree.command(
    name="uptime",
    description="Check Roblox server uptime"
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
        - server_database[server_id]["first_seen"]
    )

    await interaction.response.send_message(
        f"⏱️ Uptime: `{format_time(uptime_seconds)}`"
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
# START EVERYTHING
# =========================================================

threading.Thread(target=run_web).start()

bot.run(TOKEN)

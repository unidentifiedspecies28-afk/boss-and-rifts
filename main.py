import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
import time
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================

TOKEN = "DISCORD_TOKEN"

PLACE_ID = 13358463560
CHECK_INTERVAL = 20
DATA_FILE = "servers.json"

# Separate channels
RIFT_CHANNEL_ID = 1502236122615648326
BOSS_CHANNEL_ID = 1502236106597470288

# =========================================================
# DISCORD SETUP
# =========================================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================================================
# STORAGE
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

                    if response.status != 200:
                        print(f"API Error: {response.status}")
                        break

                    data = await response.json()

                    servers.extend(data.get("data", []))

                    cursor = data.get("nextPageCursor")

                    if not cursor:
                        break

                    await asyncio.sleep(0.15)

            except Exception as e:
                print("Fetch Error:", e)
                break

    return servers

# =========================================================
# TIME FORMAT
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

# Rifts every 1h 30m
rift = 5400

while rift <= 172800:
    RIFT_MILESTONES.append(rift)
    rift += 5400

# Bosses every 2h
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

            print(f"[NEW SERVER] {server_id}")

        else:

            server_database[server_id]["last_seen"] = current_time

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

    print(f"Tracking {len(live_servers)} live servers")

# =========================================================
# COMMANDS
# =========================================================

@bot.command()
async def uptime(ctx, server_id: str):

    if server_id not in server_database:
        await ctx.send("Server not tracked.")
        return

    uptime = (
        int(time.time())
        - server_database[server_id]["first_seen"]
    )

    await ctx.send(
        f"⏱️ Uptime: `{format_time(uptime)}`"
    )

@bot.command()
async def tracked(ctx):

    await ctx.send(
        f"Tracking `{len(server_database)}` servers."
    )

# =========================================================
# READY EVENT
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    if not server_tracker.is_running():
        server_tracker.start()

# =========================================================
# START BOT
# =========================================================

bot.run("DISCORD_TOKEN")

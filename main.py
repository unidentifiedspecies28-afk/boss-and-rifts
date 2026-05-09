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
EARLY_WARNING = 300      # 5 minutes early

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

    timeout = aiohttp.ClientTimeout(total=20)

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
                        print("RATE LIMITED")
                        await asyncio.sleep(5)
                        break

                    if response.status != 200:
                        print(f"API Error: {response.status}")
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

                    await asyncio.sleep(0.5)

            except Exception as e:
                print("Fetch Error:", e)
                break

    return servers

# =========================================================
# GET REAL CLAIMED TIME
# =========================================================

async def get_server_claimed_time(server_id):

    url = (
        "https://gamejoin.roblox.com/"
        "v1/join-game-instance"
    )

    payload = {
        "placeId": PLACE_ID,
        "gameId": server_id,
        "gameJoinAttemptId": str(server_id)
    }

    cookies = {
        ".ROBLOSECURITY": ROBLOX_COOKIE
    }

    headers = {
        "Content-Type": "application/json",
        "Referer": (
            f"https://www.roblox.com/games/"
            f"{PLACE_ID}/"
        )
    }

    timeout = aiohttp.ClientTimeout(total=20)

    try:

        async with aiohttp.ClientSession(
            cookies=cookies,
            timeout=timeout
        ) as session:

            async with session.post(
                url,
                json=payload,
                headers=headers
            ) as response:

                if response.status == 429:
                    print(
                        f"429 CLAIMED TIME {server_id}"
                    )
                    return None

                if response.status != 200:
                    return None

                data = await response.json()

                if not data:
                    return None

                join_script = data.get(
                    "joinScript"
                )

                if not join_script:
                    return None

                claimed_time = join_script.get(
                    "ServerClaimedTime"
                )

                if claimed_time:
                    return int(
                        claimed_time / 1000
                    )

    except Exception as e:
        print(
            f"Claimed Time Error: {e}"
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
        f"[{datetime.utcnow()}] "
        f"Scanning servers..."
    )

    servers = await fetch_servers()

    if not servers:
        print("No servers found.")
        return

    live_servers = set()

    for server in servers:

        server_id = server["id"]

        live_servers.add(server_id)

        # =================================================
        # NEW SERVER
        # =================================================

        if server_id not in server_database:

            claimed_time = (
                await get_server_claimed_time(
                    server_id
                )
            )

            # fallback if request fails
            if not claimed_time:

                created = server.get("created")

                if created:

                    try:

                        claimed_time = int(
                            datetime.fromisoformat(
                                created.replace(
                                    "Z",
                                    "+00:00"
                                )
                            ).timestamp()
                        )

                    except:
                        claimed_time = current_time

                else:
                    claimed_time = current_time

            server_database[server_id] = {
                "claimed_time": claimed_time,
                "last_seen": current_time,
                "rift_sent": [],
                "boss_sent": []
            }

            uptime_now = (
                current_time - claimed_time
            )

            print(
                f"[NEW SERVER] "
                f"{server_id} | "
                f"{format_time(uptime_now)}"
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
            - server_database[server_id][
                "claimed_time"
            ]
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

            alert_time = (
                spawn_time - EARLY_WARNING
            )

            remaining = (
                alert_time - uptime
            )

            if (
                -60 <= remaining <= 60
                and spawn_time not in
                server_database[server_id][
                    "rift_sent"
                ]
            ):

                channel = bot.get_channel(
                    RIFT_CHANNEL_ID
                )

                if channel:

                    real_remaining = (
                        spawn_time - uptime
                    )

                    await channel.send(
                        f"🌀 **RIFT IN 5 MINUTES**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"⌛ Rift Spawns In: "
                        f"`{format_time(real_remaining)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "rift_sent"
                ].append(spawn_time)

                print(
                    f"[RIFT ALERT] "
                    f"{server_id}"
                )

        # =================================================
        # BOSS ALERTS
        # =================================================

        for spawn_time in BOSS_TIMES:

            alert_time = (
                spawn_time - EARLY_WARNING
            )

            remaining = (
                alert_time - uptime
            )

            if (
                -60 <= remaining <= 60
                and spawn_time not in
                server_database[server_id][
                    "boss_sent"
                ]
            ):

                channel = bot.get_channel(
                    BOSS_CHANNEL_ID
                )

                if channel:

                    real_remaining = (
                        spawn_time - uptime
                    )

                    await channel.send(
                        f"👹 **BOSS IN 5 MINUTES**\n\n"
                        f"⏱️ Server Age: "
                        f"`{format_time(uptime)}`\n"
                        f"⌛ Boss Spawns In: "
                        f"`{format_time(real_remaining)}`\n"
                        f"🆔 `{server_id}`\n"
                        f"🔗 {join_link}"
                    )

                server_database[server_id][
                    "boss_sent"
                ].append(spawn_time)

                print(
                    f"[BOSS ALERT] "
                    f"{server_id}"
                )

        await asyncio.sleep(0.25)

    # =====================================================
    # REMOVE DEAD SERVERS
    # =====================================================

    dead_servers = []

    for server_id, data in server_database.items():

        if server_id not in live_servers:

            if (
                current_time
                - data["last_seen"]
                > 600
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
            del server_database[dead]

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
    description="Check bot status"
)
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(
        "🏓 Pong!"
    )

@bot.tree.command(
    name="tracked",
    description="Tracked servers"
)
async def tracked(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Tracking "
        f"`{len(server_database)}` "
        f"servers."
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
        f"⏱️ Uptime: "
        f"`{format_time(uptime_seconds)}`"
    )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    try:

        await bot.tree.sync()

        print("Slash commands synced")

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

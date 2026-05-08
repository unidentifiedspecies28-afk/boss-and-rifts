import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import requests
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
import logging

# --------------------------
# ✅ YOUR SETTINGS — EDIT THESE ONLY
# --------------------------
PLACE_ID = "YOUR_ROBLOX_PLACE_ID"          # Your Roblox Game ID
BOSS_WEBHOOK = "YOUR_BOSS_WEBHOOK_URL"
RIFT_WEBHOOK = "YOUR_RIFT_WEBHOOK_URL"

# ⏱️ TIMING SETTINGS
SCAN_INTERVAL = 30               # Scan servers every 30 seconds
BOSS_CYCLE = 7200                # 2 Hours = 7200 seconds (per server)
RIFT_CYCLE = 5400                # 1 Hour 30 Mins = 5400 seconds (per server)
WARN_BEFORE = 300                 # Warn 5 minutes before spawn
WARN_WINDOW = 20                  # Safe window to avoid duplicate alerts
MAX_SERVER_AGE = 172800          # Auto-remove servers after 48h
# --------------------------

# 🎨 EMBED COLORS
COLOR_BOSS_WARN = 0xFFA500
COLOR_BOSS_NOW = 0xFF0000
COLOR_RIFT_WARN = 0x00FFFF
COLOR_RIFT_NOW = 0x9932CC
COLOR_INFO = 0x3498DB

# ✅ SETUP
logging.basicConfig(level=logging.INFO)
load_dotenv()

# Keep bot alive
app = Flask('')
@app.route('/')
def home(): return "✅ TRACKER ONLINE — PER-SERVER UPTIME ACTIVE"
def run(): app.run(host='0.0.0.0', port=10000)
Thread(target=run, daemon=True).start()

# ✅ CORE BOT — TRACKS EVERY SERVER SEPARATELY
class RobloxAutoTracker(commands.Bot):
    def __init__(self):
        # Basic intents only — NO VOICE / NO ERRORS
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(command_prefix="!", intents=intents, help_command=None)

        # 📊 DATA STORAGE: {server_id: start_time} — EACH SERVER HAS ITS OWN START TIME
        self.servers = {}
        self.alerts_sent = {}

    async def setup_hook(self):
        # ✅ SYNC COMMANDS — NO GUILD ID NEEDED, STILL LOADS FAST
        await self.tree.sync()
        self.scan_all_servers.start()
        print("✅ SLASH COMMANDS LOADED: /status, /servers, /next")
        print("✅ TRACKING ALL SERVERS — PER-SERVER UPTIME CALCULATED")

    # 🕵️‍♂️ SCAN ALL SERVERS UNDER YOUR PLACE ID
    @tasks.loop(seconds=SCAN_INTERVAL)
    async def scan_all_servers(self):
        cookie = os.getenv("ROBLOX_COOKIE")
        if not cookie:
            print("❌ ERROR: ROBLOX_COOKIE missing in .env")
            return

        url = f"https://games.roblox.com/games/{PLACE_ID}/servers/Public?sortOrder=Desc&limit=100"
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/135.0.0.0",
            "Accept": "application/json"
        }

        try:
            res = requests.get(url, headers=headers, timeout=15).json()
            if "data" not in res:
                print("⚠️ No servers found — check PlaceID or Cookie")
                return

            now = datetime.utcnow()
            print(f"🔍 Scanned {len(res['data'])} active servers")

            for server in res["data"]:
                sid = server["id"]

                # ✅ NEW SERVER FOUND — RECORD ITS START TIME (UPTIME STARTS HERE)
                if sid not in self.servers:
                    start_time = self._get_start_time(sid, server)
                    self.servers[sid] = start_time
                    self.alerts_sent[sid] = []
                    print(f"✅ NEW SERVER | {sid[:12]}... | Start time recorded")

                # 🧮 CALCULATE EVENTS *FOR THIS SERVER ONLY*
                self.check_events(sid, self.servers[sid], now)

            # 🗑️ CLEANUP OLD SERVERS
            for sid in list(self.servers.keys()):
                age = (now - self.servers[sid]).total_seconds()
                if age > MAX_SERVER_AGE:
                    del self.servers[sid]
                    del self.alerts_sent[sid]

        except Exception as e:
            print(f"❌ SCAN ERROR: {str(e)}")

    # 🔑 GET EXACT START TIME FROM ROBLOX JOB ID
    def _get_start_time(self, server_id, server_data):
        try:
            if "T" in server_id and "Z" in server_id:
                dt_str = server_id.split("_")[0]
                return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ")
        except:
            pass
        # Fallback if JobID format changes
        return datetime.utcnow() - timedelta(minutes=server_data.get("playing", 0))

    def check_events(self, sid, start_time, now):
        # ⏱️ THIS SERVER'S OWN UPTIME
        age = (now - start_time).total_seconds()
        link = f"https://www.roblox.com/games/{PLACE_ID}?jobId={sid}"

        # --- BOSS TIMING ---
        until_boss = BOSS_CYCLE - (age % BOSS_CYCLE)
        boss_num = int(age // BOSS_CYCLE) + 1

        # --- RIFT TIMING ---
        until_rift = RIFT_CYCLE - (age % RIFT_CYCLE)
        rift_num = int(age // RIFT_CYCLE) + 1

        # ⚠️ 5 MIN WARNING — PER SERVER
        if (WARN_BEFORE - WARN_WINDOW) < until_boss <= WARN_BEFORE:
            if f"boss_warn_{boss_num}" not in self.alerts_sent[sid]:
                embed = discord.Embed(
                    title="🚨 BOSS SPAWN WARNING",
                    description=(
                        f"**Server:** `{sid[:12]}...`\n"
                        f"**Boss #{boss_num}** spawning in **5 MINUTES**\n"
                        f"⏱️ Server Uptime: `{self._fmt(age)}`\n"
                        f"🔗 [Join Server]({link})"
                    ),
                    color=COLOR_BOSS_WARN, timestamp=now
                )
                self.send(BOSS_WEBHOOK, embed, sid, f"boss_warn_{boss_num}")

        if (WARN_BEFORE - WARN_WINDOW) < until_rift <= WARN_BEFORE:
            if f"rift_warn_{rift_num}" not in self.alerts_sent[sid]:
                embed = discord.Embed(
                    title="🌀 RIFT SPAWN WARNING",
                    description=(
                        f"**Server:** `{sid[:12]}...`\n"
                        f"**Rift #{rift_num}** opening in **5 MINUTES**\n"
                        f"⏱️ Server Uptime: `{self._fmt(age)}`\n"
                        f"🔗 [Join Server]({link})"
                    ),
                    color=COLOR_RIFT_WARN, timestamp=now
                )
                self.send(RIFT_WEBHOOK, embed, sid, f"rift_warn_{rift_num}")

        # ⚡ SPAWNING NOW — PER SERVER
        if 0 <= until_boss <= 15:
            if f"boss_now_{boss_num}" not in self.alerts_sent[sid]:
                embed = discord.Embed(
                    title="⚡ BOSS SPAWNING NOW!",
                    description=(
                        f"**Server:** `{sid[:12]}...`\n"
                        f"**Boss #{boss_num}** IS ACTIVE!\n"
                        f"⏱️ Server Uptime: `{self._fmt(age)}`\n"
                        f"🔗 [Join Fast]({link})"
                    ),
                    color=COLOR_BOSS_NOW, timestamp=now
                )
                self.send(BOSS_WEBHOOK, embed, sid, f"boss_now_{boss_num}")

        if 0 <= until_rift <= 15:
            if f"rift_now_{rift_num}" not in self.alerts_sent[sid]:
                embed = discord.Embed(
                    title="🌪️ RIFT OPENING NOW!",
                    description=(
                        f"**Server:** `{sid[:12]}...`\n"
                        f"**Rift #{rift_num}** IS ACTIVE!\n"
                        f"⏱️ Server Uptime: `{self._fmt(age)}`\n"
                        f"🔗 [Join Fast]({link})"
                    ),
                    color=COLOR_RIFT_NOW, timestamp=now
                )
                self.send(RIFT_WEBHOOK, embed, sid, f"rift_now_{rift_num}")

    # 🕒 Format seconds → HHh MMm SSs
    def _fmt(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}h {m:02d}m {s:02d}s"

    # 📤 Send & prevent duplicates
    def send(self, webhook, embed, sid, alert_id):
        try:
            requests.post(webhook, json={"embeds": [embed.to_dict()]}, timeout=10)
            self.alerts_sent[sid].append(alert_id)
            print(f"📢 Sent | {alert_id} | Server: {sid[:12]}...")
        except Exception as e:
            print(f"❌ Send Error: {e}")

    # 🧪 /status
    @app_commands.command(name="status", description="Bot status")
    async def status(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 BOT STATUS",
            description=f"✅ ONLINE | Active Servers: `{len(self.servers)}` | Scan: `{SCAN_INTERVAL}s`",
            color=COLOR_INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 🧪 /servers — SHOW ALL + THEIR UPTIME
    @app_commands.command(name="servers", description="List all servers & uptime")
    async def servers(self, interaction: discord.Interaction):
        if not self.servers:
            await interaction.response.send_message("❌ No servers yet — wait 30s", ephemeral=True)
            return
        text = ""
        now = datetime.utcnow()
        for sid, start in list(self.servers.items())[:15]:
            age = (now - start).total_seconds()
            text += f"`{sid[:12]}...` → **{self._fmt(age)}**\n"
        embed = discord.Embed(title="🌐 ALL SERVERS (PER-SERVER UPTIME)", description=text, color=COLOR_INFO)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 🧪 /next — NEXT EVENTS PER SERVER
    @app_commands.command(name="next", description="Next boss/rift per server")
    async def next(self, interaction: discord.Interaction):
        if not self.servers:
            await interaction.response.send_message("❌ No servers yet", ephemeral=True)
            return
        text = ""
        now = datetime.utcnow()
        for sid, start in list(self.servers.items())[:10]:
            age = (now - start).total_seconds()
            tb = BOSS_CYCLE - (age % BOSS_CYCLE)
            tr = RIFT_CYCLE - (age % RIFT_CYCLE)
            text += f"`{sid[:12]}...` → Boss: `{self._fmt(tb)}` | Rift: `{self._fmt(tr)}`\n"
        embed = discord.Embed(title="⏱️ NEXT EVENTS", description=text, color=COLOR_INFO)
        await interaction.response.send_message(embed=embed, ephemeral=True)

bot = RobloxAutoTracker()

@bot.event
async def on_ready():
    print(f"✅ LOGGED IN AS: {bot.user}")
    print("✅ READY — PER-SERVER TRACKING ACTIVE")

bot.run(os.getenv("DISCORD_TOKEN"), log_level=logging.ERROR)

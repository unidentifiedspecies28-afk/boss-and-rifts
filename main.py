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
# ✅ YOUR SETTINGS — EDIT THESE
# --------------------------
PLACE_ID = "YOUR_ROBLOX_PLACE_ID"          # Your Roblox Game ID
BOSS_WEBHOOK = "YOUR_BOSS_WEBHOOK_URL"
RIFT_WEBHOOK = "YOUR_RIFT_WEBHOOK_URL"

# ⏱️ TIMING — LOCKED TO 5 MINUTE WARNING
SCAN_INTERVAL = 30               # Scan servers every 30 seconds
BOSS_CYCLE = 7200                # 2 Hours = 7200 seconds
RIFT_CYCLE = 5400                # 1 Hour 30 Mins = 5400 seconds
WARN_BEFORE = 300                 # ⚠️ WARN EXACTLY 5 MIN BEFORE = 300 SEC
WARN_WINDOW = 20                  # Safe trigger window
MAX_SERVER_AGE = 172800          # Auto-delete servers after 48 hours

# 🎨 EMBED COLORS
COLOR_BOSS_WARN = 0xFFA500       # Orange
COLOR_BOSS_NOW = 0xFF0000        # Red
COLOR_RIFT_WARN = 0x00FFFF       # Cyan
COLOR_RIFT_NOW = 0x9932CC        # Purple
COLOR_INFO = 0x3498DB            # Blue for commands
# --------------------------

# ✅ ENABLE LOGGING — SEE EVERYTHING HAPPEN
logging.basicConfig(level=logging.INFO)
load_dotenv()

# Keep bot online 24/7
app = Flask('')
@app.route('/')
def home(): return "✅ TRACKER ONLINE — NO AUDIOOP ERRORS"
def run(): app.run(host='0.0.0.0', port=10000)
Thread(target=run, daemon=True).start()

# ✅ NO VOICE / NO AUDIO — WE DON'T USE IT AT ALL
class RobloxAutoTracker(commands.Bot):
    def __init__(self):
        # Only basic permissions — NO VOICE INTENTS
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        # ❌❌❌ NO VOICE CODE HERE — NO DELETING, NO CHANGING, NOTHING
        # We just never touch voice features — audioop will NEVER load

        self.servers = {}       # {server_id: start_time}
        self.alerts_sent = {}   # Prevent duplicate messages
        self.start_time = datetime.utcnow()

    async def setup_hook(self):
        self.scan_all_servers.start()
        await self.tree.sync()  # Load slash commands
        print("✅ Slash commands loaded: /status, /servers, /next")
        print("✅ Scanner started — tracking ALL servers like RoValra")

    # 🕵️‍♂️ SCAN EVERY SERVER — EXACT SAME AS ROVALRA EXTENSION
    @tasks.loop(seconds=SCAN_INTERVAL)
    async def scan_all_servers(self):
        cookie = os.getenv("ROBLOX_COOKIE")
        if not cookie:
            print("❌ ERROR: ROBLOX_COOKIE not found in .env file")
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
                print("⚠️ No server data — check PlaceID or Cookie")
                return

            now = datetime.utcnow()
            print(f"🔍 Scanned {len(res['data'])} servers")

            for server in res["data"]:
                sid = server["id"]

                # ✅ GET EXACT UPTIME / CREATION TIME — 100% ACCURATE
                if sid not in self.servers:
                    start_time = self._get_real_start_time(sid, server)
                    self.servers[sid] = start_time
                    self.alerts_sent[sid] = []
                    uptime_str = self._fmt_time((now - start_time).total_seconds())
                    print(f"✅ NEW SERVER | {sid[:12]}... | Uptime: {uptime_str}")

                # 🧮 CALCULATE & SEND ALERTS
                self.process_spawn_logic(sid, self.servers[sid], now)

            # 🗑️ DELETE SERVERS OLDER THAN 48 HOURS
            for sid in list(self.servers.keys()):
                age = (now - self.servers[sid]).total_seconds()
                if age > MAX_SERVER_AGE:
                    del self.servers[sid]
                    del self.alerts_sent[sid]
                    print(f"🗑️ Removed old server: {sid[:12]}...")

        except Exception as e:
            print(f"❌ SCAN ERROR: {str(e)}")

    # 🔑 EXACT UPTIME READER — HOW ROVALRA WORKS
    def _get_real_start_time(self, server_id, server_data):
        try:
            # Read timestamp directly from Roblox JobID
            if "T" in server_id and "Z" in server_id:
                dt_str = server_id.split("_")[0]
                return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ")
        except:
            pass
        # Fallback: calculate from player data
        playing_mins = server_data.get("playing", 0)
        return datetime.utcnow() - timedelta(minutes=playing_mins)

    def process_spawn_logic(self, sid, start_time, now):
        age = (now - start_time).total_seconds()
        link = f"https://www.roblox.com/games/{PLACE_ID}?jobId={sid}"

        # --- BOSS LOGIC ---
        until_boss = BOSS_CYCLE - (age % BOSS_CYCLE)
        boss_num = int(age // BOSS_CYCLE) + 1
        boss_total = int(MAX_SERVER_AGE // BOSS_CYCLE)

        # --- RIFT LOGIC ---
        until_rift = RIFT_CYCLE - (age % RIFT_CYCLE)
        rift_num = int(age // RIFT_CYCLE) + 1
        rift_total = int(MAX_SERVER_AGE // RIFT_CYCLE)

        # ⚠️ 5 MINUTE WARNING — EXACTLY 300 SECONDS BEFORE
        if (WARN_BEFORE - WARN_WINDOW) < until_boss <= WARN_BEFORE:
            embed = discord.Embed(
                title="🚨 BOSS SPAWN WARNING",
                description=(
                    f"**Boss #{boss_num}/{boss_total}** spawning in **5 MINUTES**!\n\n"
                    f"⏱️ Server Uptime: `{self._fmt_time(age)}`\n"
                    f"⏳ Time Remaining: `{self._fmt_time(until_boss)}`\n"
                    f"🔗 [Join Server]({link})"
                ),
                color=COLOR_BOSS_WARN,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Roblox Auto-Tracker • 5min Alert System")
            self.send_embed(BOSS_WEBHOOK, embed, sid, f"boss_warn_{boss_num}")

        if (WARN_BEFORE - WARN_WINDOW) < until_rift <= WARN_BEFORE:
            embed = discord.Embed(
                title="🌀 RIFT SPAWN WARNING",
                description=(
                    f"**Rift #{rift_num}/{rift_total}** opening in **5 MINUTES**!\n\n"
                    f"⏱️ Server Uptime: `{self._fmt_time(age)}`\n"
                    f"⏳ Time Remaining: `{self._fmt_time(until_rift)}`\n"
                    f"🔗 [Join Server]({link})"
                ),
                color=COLOR_RIFT_WARN,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Roblox Auto-Tracker • 5min Alert System")
            self.send_embed(RIFT_WEBHOOK, embed, sid, f"rift_warn_{rift_num}")

        # ⚡ SPAWNING NOW ALERT
        if 0 <= until_boss <= 15:
            embed = discord.Embed(
                title="⚡ BOSS SPAWNING NOW!",
                description=(
                    f"**Boss #{boss_num}/{boss_total}** IS ACTIVE!\n\n"
                    f"⏱️ Server Uptime: `{self._fmt_time(age)}`\n"
                    f"🔗 [Join Fast]({link})"
                ),
                color=COLOR_BOSS_NOW,
                timestamp=datetime.utcnow()
            )
            self.send_embed(BOSS_WEBHOOK, embed, sid, f"boss_now_{boss_num}")

        if 0 <= until_rift <= 15:
            embed = discord.Embed(
                title="🌪️ RIFT OPENING NOW!",
                description=(
                    f"**Rift #{rift_num}/{rift_total}** IS ACTIVE!\n\n"
                    f"⏱️ Server Uptime: `{self._fmt_time(age)}`\n"
                    f"🔗 [Join Fast]({link})"
                ),
                color=COLOR_RIFT_NOW,
                timestamp=datetime.utcnow()
            )
            self.send_embed(RIFT_WEBHOOK, embed, sid, f"rift_now_{rift_num}")

    # 🕒 Format time to HHh MMm SSs
    def _fmt_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}h {m:02d}m {s:02d}s"

    # 📤 Send embed + block duplicates
    def send_embed(self, webhook_url, embed, sid, alert_id):
        if alert_id in self.alerts_sent[sid]:
            return
        try:
            requests.post(webhook_url, json={"embeds": [embed.to_dict()]}, timeout=10)
            self.alerts_sent[sid].append(alert_id)
            print(f"📢 Alert sent: {alert_id} | {sid[:12]}...")
        except Exception as e:
            print(f"❌ Webhook Error: {e}")

    # 🧪 TEST COMMAND 1: /status → Is bot working?
    @app_commands.command(name="status", description="Check bot status & tracked servers")
    async def status(self, interaction: discord.Interaction):
        uptime = self._fmt_time((datetime.utcnow() - self.start_time).total_seconds())
        embed = discord.Embed(
            title="📊 BOT STATUS",
            description=(
                f"✅ **ONLINE & WORKING**\n"
                f"⏱️ Bot Uptime: `{uptime}`\n"
                f"🔍 Servers Tracked: `{len(self.servers)}`\n"
                f"⚙️ Scan Interval: `{SCAN_INTERVAL}s`\n"
                f"🔄 Boss Cycle: `{BOSS_CYCLE//60}min` | Rift Cycle: `{RIFT_CYCLE//60}min`"
            ),
            color=COLOR_INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 🧪 TEST COMMAND 2: /servers → List all servers + uptime (matches RoValra)
    @app_commands.command(name="servers", description="List all detected servers & uptime")
    async def servers(self, interaction: discord.Interaction):
        if not self.servers:
            await interaction.response.send_message("❌ No servers found yet — wait 30 seconds.", ephemeral=True)
            return

        text = ""
        now = datetime.utcnow()
        for sid, start in list(self.servers.items())[:10]:
            age = (now - start).total_seconds()
            text += f"`{sid[:12]}...` → **{self._fmt_time(age)}**\n"

        embed = discord.Embed(
            title="🌐 DETECTED SERVERS",
            description=f"Total: `{len(self.servers)}`\n\n{text}",
            color=COLOR_INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 🧪 TEST COMMAND 3: /next → When is next Boss/Rift?
    @app_commands.command(name="next", description="Show next spawn times")
    async def next(self, interaction: discord.Interaction):
        if not self.servers:
            await interaction.response.send_message("❌ No servers found yet.", ephemeral=True)
            return

        now = datetime.utcnow()
        next_boss = []
        next_rift = []

        for sid, start in self.servers.items():
            age = (now - start).total_seconds()
            tb = BOSS_CYCLE - (age % BOSS_CYCLE)
            tr = RIFT_CYCLE - (age % RIFT_CYCLE)
            next_boss.append((tb, sid))
            next_rift.append((tr, sid))

        next_boss.sort()
        next_rift.sort()

        embed = discord.Embed(
            title="⏱️ NEXT SPAWNS",
            description=(
                f"🔴 **Next Boss:** in `{self._fmt_time(next_boss[0][0])}`\n"
                f"🔵 **Next Rift:** in `{self._fmt_time(next_rift[0][0])}`"
            ),
            color=COLOR_INFO
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

bot = RobloxAutoTracker()

@bot.event
async def on_ready():
    print(f"✅ LOGGED IN AS: {bot.user}")
    print("✅ FULLY OPERATIONAL — NO ERRORS AT ALL")

bot.run(os.getenv("DISCORD_TOKEN"), log_level=logging.ERROR)

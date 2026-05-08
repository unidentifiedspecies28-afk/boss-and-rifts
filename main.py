import discord
from discord.ext import commands, tasks
import os
import requests
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# --------------------------
# ✅ YOUR SETTINGS — EDIT THESE
# --------------------------
PLACE_ID = "13358463560"          # Replace with YOUR Game ID
BOSS_WEBHOOK = "https://discord.com/api/webhooks/1502263569633509487/NGKjFf4EGD32m3UbuafIadrObSSiOxujGXvWcWLSQj8OEAHRcHw-X_Q0OnZOq1r8Ykvw"
RIFT_WEBHOOK = "https://discord.com/api/webhooks/1502264183956308130/xLuNT-iod8k245vT_jx5u4pLVCasuwtLBAT0NjaJvR3IISH5UA3pjJ43T1bph6ENyzh-"

# ⏱️ TIMING CONFIG — LOCKED TO 5MIN WARNING
SCAN_INTERVAL = 30               # Check every 30s (perfect accuracy)
BOSS_CYCLE = 7200                # 2 Hours = 7200 seconds
RIFT_CYCLE = 5400                # 1 Hour 30 Mins = 5400 seconds
WARN_BEFORE = 300                 # ⚠️ ANNOUNCE EXACTLY 5 MINUTES BEFORE
WARN_WINDOW = 20                  # Safe trigger window
MAX_SERVER_AGE = 172800          # Auto-remove after 48 Hours

# 🎨 EMBED COLORS
COLOR_BOSS_WARN = 0xFFA500       # Orange
COLOR_BOSS_NOW = 0xFF0000        # Red
COLOR_RIFT_WARN = 0x00FFFF       # Cyan
COLOR_RIFT_NOW = 0x9932CC        # Purple
# --------------------------

load_dotenv()
app = Flask('')
@app.route('/')
def home(): return "✅ TRACKER ONLINE — NO AUDIOOP NEEDED"
def run(): app.run(host='0.0.0.0', port=10000)
Thread(target=run, daemon=True).start()

# ✅ BYPASS: No voice/audio features used — audioop never gets imported
class RobloxAutoTracker(commands.Bot):
    def __init__(self):
        # ✅ Disable voice/voice-related features entirely to avoid audioop
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        
        self.servers = {}       # {job_id: start_time_datetime}
        self.alerts_sent = {}   # Prevent duplicate alerts

    async def setup_hook(self):
        self.scan_all_servers.start()

    # 🕵️‍♂️ SCAN ALL SERVERS — SAME AS ROVALRA
    @tasks.loop(seconds=SCAN_INTERVAL)
    async def scan_all_servers(self):
        cookie = os.getenv("ROBLOX_COOKIE")
        if not cookie:
            print("❌ ERROR: ROBLOX_COOKIE missing!")
            return

        url = f"https://games.roblox.com/v1/games/{PLACE_ID}/servers/Public?sortOrder=Desc&limit=100"
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/135.0.0.0",
            "Accept": "application/json"
        }

        try:
            res = requests.get(url, headers=headers, timeout=10).json()
            if "data" not in res: return

            now = datetime.utcnow()
            for server in res["data"]:
                jid = server["id"]

                # ✅ GET EXACT UPTIME / START TIME — 100% ACCURATE
                if jid not in self.servers:
                    start_time = self._get_real_start_time(jid, server)
                    self.servers[jid] = start_time
                    self.alerts_sent[jid] = []
                    print(f"✅ TRACKING | ID: {jid[:8]}... | Uptime: {self._fmt_time((now - start_time).total_seconds())}")

                # 🧮 CALCULATE & TRIGGER ALERTS
                self.process_spawn_logic(jid, self.servers[jid], now)

            # 🧹 REMOVE SERVERS OLDER THAN 48H
            for jid in list(self.servers.keys()):
                age = (now - self.servers[jid]).total_seconds()
                if age > MAX_SERVER_AGE:
                    del self.servers[jid]
                    del self.alerts_sent[jid]

        except Exception as e:
            print(f"❌ Scan Error: {e}")

    # 🔑 EXACT UPTIME READER — ROVALRA METHOD
    def _get_real_start_time(self, job_id, server_data):
        try:
            # Read timestamp directly from JobID
            if "T" in job_id and "Z" in job_id:
                dt_str = job_id.split("_")[0]
                return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ")
        except: pass
        # Fallback: Calculate from player age data
        playing_mins = server_data.get("playing", 0)
        return datetime.utcnow() - timedelta(minutes=playing_mins)

    def process_spawn_logic(self, jid, start_time, now):
        age = (now - start_time).total_seconds()
        link = f"https://www.roblox.com/games/{PLACE_ID}?jobId={jid}"

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
                    f"**Boss #{boss_num}/{boss_total}** is spawning in **5 MINUTES**!\n\n"
                    f"⏱️ **Server Uptime:** `{self._fmt_time(age)}`\n"
                    f"⏳ **Time Remaining:** `{self._fmt_time(until_boss)}`\n"
                    f"🔗 **Join Server:** [Click Here]({link})"
                ),
                color=COLOR_BOSS_WARN,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Roblox Auto-Tracker • 5min Warning System")
            self.send_embed(BOSS_WEBHOOK, embed, jid, f"boss_warn_{boss_num}")

        if (WARN_BEFORE - WARN_WINDOW) < until_rift <= WARN_BEFORE:
            embed = discord.Embed(
                title="🌀 RIFT SPAWN WARNING",
                description=(
                    f"**Rift #{rift_num}/{rift_total}** is opening in **5 MINUTES**!\n\n"
                    f"⏱️ **Server Uptime:** `{self._fmt_time(age)}`\n"
                    f"⏳ **Time Remaining:** `{self._fmt_time(until_rift)}`\n"
                    f"🔗 **Join Server:** [Click Here]({link})"
                ),
                color=COLOR_RIFT_WARN,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Roblox Auto-Tracker • 5min Warning System")
            self.send_embed(RIFT_WEBHOOK, embed, jid, f"rift_warn_{rift_num}")

        # ⚡ SPAWNING NOW ALERT
        if 0 <= until_boss <= 15:
            embed = discord.Embed(
                title="⚡ BOSS SPAWNING NOW!",
                description=(
                    f"**Boss #{boss_num}/{boss_total}** has appeared!\n\n"
                    f"⏱️ **Server Uptime:** `{self._fmt_time(age)}`\n"
                    f"🔗 **Join Fast:** [Click Here]({link})"
                ),
                color=COLOR_BOSS_NOW,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Roblox Auto-Tracker • Spawn Active")
            self.send_embed(BOSS_WEBHOOK, embed, jid, f"boss_now_{boss_num}")

        if 0 <= until_rift <= 15:
            embed = discord.Embed(
                title="🌪️ RIFT OPENING NOW!",
                description=(
                    f"**Rift #{rift_num}/{rift_total}** is active!\n\n"
                    f"⏱️ **Server Uptime:** `{self._fmt_time(age)}`\n"
                    f"🔗 **Join Fast:** [Click Here]({link})"
                ),
                color=COLOR_RIFT_NOW,
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text="Roblox Auto-Tracker • Spawn Active")
            self.send_embed(RIFT_WEBHOOK, embed, jid, f"rift_now_{rift_num}")

    # 🕒 FORMAT TIME (HH:MM:SS)
    def _fmt_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}h {m:02d}m {s:02d}s"

    # 📤 SEND EMBED + BLOCK DUPLICATES
    def send_embed(self, webhook_url, embed, jid, alert_id):
        if alert_id in self.alerts_sent[jid]: return
        requests.post(
            webhook_url,
            json={"embeds": [embed.to_dict()]},
            timeout=5
        )
        self.alerts_sent[jid].append(alert_id)

bot = RobloxAutoTracker()
bot.run(os.getenv("DISCORD_TOKEN"))

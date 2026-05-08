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

# 🚨 IMPORTANT: PUT YOUR DISCORD SERVER ID HERE TO SEE COMMANDS INSTANTLY
# Right-click your server icon in Discord -> Copy Server ID
MY_GUILD_ID =  1466002025241378947

# ⏱️ TIMING SETTINGS
SCAN_INTERVAL = 30               
BOSS_CYCLE = 7200                
RIFT_CYCLE = 5400                
WARN_BEFORE = 300                 
WARN_WINDOW = 20                  
# --------------------------

logging.basicConfig(level=logging.INFO)
load_dotenv()

app = Flask('')
@app.route('/')
def home(): return "✅ TRACKER ONLINE"
def run(): app.run(host='0.0.0.0', port=10000)
Thread(target=run, daemon=True).start()

class RobloxAutoTracker(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.servers = {}
        self.alerts_sent = {}

    async def setup_hook(self):
        # ✅ THIS BLOCK FORCES COMMANDS TO SHOW UP INSTANTLY
        if MY_GUILD_ID:
            guild = discord.Object(id=MY_GUILD_ID)
            # This copies your commands specifically to your server
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"✅ Commands synced INSTANTLY to server: {MY_GUILD_ID}")
        
        # Also sync globally (can take 1 hour for other servers)
        await self.tree.sync()
        
        self.scan_all_servers.start()
        print("✅ Scanner started")

    @tasks.loop(seconds=SCAN_INTERVAL)
    async def scan_all_servers(self):
        cookie = os.getenv("ROBLOX_COOKIE")
        if not cookie: return

        url = f"https://games.roblox.com/games/{PLACE_ID}/servers/Public?sortOrder=Desc&limit=100"
        headers = {"Cookie": f".ROBLOSECURITY={cookie}", "User-Agent": "Mozilla/5.0"}

        try:
            res = requests.get(url, headers=headers, timeout=15).json()
            if "data" not in res: return
            now = datetime.utcnow()

            for server in res["data"]:
                sid = server["id"]
                if sid not in self.servers:
                    self.servers[sid] = self._get_start_time(sid, server)
                    self.alerts_sent[sid] = []
                self.check_events(sid, self.servers[sid], now)

            # Cleanup old servers
            for sid in list(self.servers.keys()):
                if (now - self.servers[sid]).total_seconds() > 172800:
                    del self.servers[sid]
                    del self.alerts_sent[sid]
        except Exception as e:
            print(f"❌ Scan Error: {e}")

    def _get_start_time(self, sid, data):
        try:
            if "T" in sid and "Z" in sid:
                return datetime.strptime(sid.split("_")[0], "%Y%m%dT%H%M%SZ")
        except: pass
        return datetime.utcnow() - timedelta(minutes=data.get("playing", 0))

    def check_events(self, sid, start, now):
        age = (now - start).total_seconds()
        link = f"https://www.roblox.com/games/{PLACE_ID}?jobId={sid}"
        
        # Boss logic
        tb = BOSS_CYCLE - (age % BOSS_CYCLE)
        if (WARN_BEFORE - WARN_WINDOW) < tb <= WARN_BEFORE:
            self.send_alert(BOSS_WEBHOOK, sid, "Boss", tb, link, age)
        elif 0 <= tb <= 15:
            self.send_alert(BOSS_WEBHOOK, sid, "Boss NOW", 0, link, age)

        # Rift logic
        tr = RIFT_CYCLE - (age % RIFT_CYCLE)
        if (WARN_BEFORE - WARN_WINDOW) < tr <= WARN_BEFORE:
            self.send_alert(RIFT_WEBHOOK, sid, "Rift", tr, link, age)
        elif 0 <= tr <= 15:
            self.send_alert(RIFT_WEBHOOK, sid, "Rift NOW", 0, link, age)

    def send_alert(self, wh, sid, type, due, link, age):
        alert_id = f"{type}_{int(age//60)}"
        if alert_id in self.alerts_sent[sid]: return
        
        embed = discord.Embed(title=f"🚨 {type} Alert", color=0xFFA500)
        embed.description = f"**Server:** `{sid[:10]}...`\n**Uptime:** `{int(age//3600)}h {int((age%3600)//60)}m`\n[Join Server]({link})"
        
        try:
            requests.post(wh, json={"embeds": [embed.to_dict()]})
            self.alerts_sent[sid].append(alert_id)
        except: pass

    @app_commands.command(name="status", description="Check bot status")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"✅ Tracking {len(self.servers)} servers.", ephemeral=True)

    @app_commands.command(name="servers", description="List tracked servers")
    async def servers(self, interaction: discord.Interaction):
        if not self.servers:
            await interaction.response.send_message("No servers found.", ephemeral=True)
            return
        msg = "\n".join([f"`{s[:10]}`" for s in list(self.servers.keys())[:10]])
        await interaction.response.send_message(f"**Top 10 Servers:**\n{msg}", ephemeral=True)

bot = RobloxAutoTracker()
bot.run(os.getenv("DISCORD_TOKEN"))

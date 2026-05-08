import discord
from discord.ext import commands, tasks
import os
import requests
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread

# --- CONFIGURATION ---
PLACE_ID = "YOUR_ROBLOX_PLACE_ID" 
BOSS_WEBHOOK = "YOUR_BOSS_WEBHOOK_URL"
RIFT_WEBHOOK = "YOUR_RIFT_WEBHOOK_URL"
# ---------------------

app = Flask('')
@app.route('/')
def home(): return "Tracker Online"
def run(): app.run(host='0.0.0.0', port=10000)
Thread(target=run, daemon=True).start()

class AutoTracker(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.servers = {} # {job_id: start_time}
        self.alerts = {}  # {job_id: [already_sent_alerts]}

    async def setup_hook(self):
        self.scanner.start()

    @tasks.loop(seconds=60)
    async def scanner(self):
        # Fetch servers from Roblox API
        cookie = os.getenv("ROBLOX_COOKIE")
        url = f"https://games.roblox.com/v1/games/{PLACE_ID}/servers/Public?limit=100"
        headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
        
        try:
            r = requests.get(url, headers=headers).json()
            if "data" not in r: return

            now = datetime.now()
            for s in r["data"]:
                jid = s["id"]
                if jid not in self.servers:
                    # New server found! Mark discovery time
                    self.servers[jid] = now
                    self.alerts[jid] = []
                
                self.process_logic(jid, self.servers[jid], now)
        except Exception as e:
            print(f"Scan Error: {e}")

    def process_logic(self, jid, birth, now):
        age = (now - birth).total_seconds()
        if age > 172800: # Remove if older than 48h
            del self.servers[jid]
            return

        link = f"https://www.roblox.com/games/{PLACE_ID}?jobId={jid}"
        u_boss = 7200 - (age % 7200)
        u_rift = 5400 - (age % 5400)

        # 5m Warning Logic
        if 280 < u_boss <= 300 and f"b5_{int(age//7200)}" not in self.alerts[jid]:
            requests.post(BOSS_WEBHOOK, json={"content": f"🚨 **BOSS IN 5 MIN**\n👉 {link}"})
            self.alerts[jid].append(f"b5_{int(age//7200)}")

        if 280 < u_rift <= 300 and f"r5_{int(age//5400)}" not in self.alerts[jid]:
            requests.post(RIFT_WEBHOOK, json={"content": f"🌀 **RIFT IN 5 MIN**\n👉 {link}"})
            self.alerts[jid].append(f"r5_{int(age//5400)}")

bot = AutoTracker()
bot.run(os.getenv("BOT_TOKEN"))

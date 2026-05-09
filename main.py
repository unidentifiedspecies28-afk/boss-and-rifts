import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# --------------------------
# ✅ SETTINGS
# --------------------------
PLACE_ID = "13358463560"  
BOSS_WEBHOOK = "YOUR_BOSS_WEBHOOK_URL"
RIFT_WEBHOOK = "YOUR_RIFT_WEBHOOK_URL"
MY_GUILD_ID = 1466002025241378947  # Your Server ID

# BOSS = 2 hours (7200s) | RIFT = 1.5 hours (5400s)
BOSS_CYCLE = 7200
RIFT_CYCLE = 5400
# --------------------------

load_dotenv()

class TesterBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.servers = {}
        self.alerts_sent = {}

    async def setup_hook(self):
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.scan_loop.start()

    def get_roblox_data(self):
        """This is the core scanner logic"""
        cookie = os.getenv("ROBLOX_COOKIE")
        # limit=50 is more stable than 100
        url = f"https://games.roblox.com/v1/games/{PLACE_ID}/servers/Public?limit=50"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Cookie": f".ROBLOSECURITY={cookie}" if cookie else ""
        }
        try:
            r = requests.get(url, headers=headers, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    @tasks.loop(seconds=30)
    async def scan_loop(self):
        data = self.get_roblox_data()
        if "data" in data:
            now = datetime.utcnow()
            for server in data["data"]:
                sid = server["id"]
                if sid not in self.servers:
                    # Uptime calculation
                    self.servers[sid] = now - timedelta(minutes=server.get("playing", 0))
                    self.alerts_sent[sid] = []
                
                # Check for Boss/Rift warnings here (Logic from previous message)

    @app_commands.command(name="test_now", description="Force a scan and report results")
    async def test_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = self.get_roblox_data()
        
        if "data" in data:
            count = len(data["data"])
            msg = f"✅ Success! Found **{count}** active servers.\n"
            if count > 0:
                first_server = data["data"][0]
                msg += f"First Server ID: `{first_server['id'][:10]}...`\n"
                msg += f"Players: `{first_server['playing']}/{first_server['maxPlayers']}`"
            await interaction.followup.send(msg)
        else:
            error_msg = data.get("errors", [{}])[0].get("message", "Unknown Error")
            await interaction.followup.send(f"❌ Failed! Roblox API said: `{error_msg}`\n(This usually means you need a valid ROBLOX_COOKIE)")

bot = TesterBot()
bot.run(os.getenv("DISCORD_TOKEN"))

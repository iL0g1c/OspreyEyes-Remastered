import discord
from discord import app_commands
from discord.ext import commands
import tracemalloc
from dotenv import load_dotenv
import os
from flask import Flask, request
from threading import Thread

tracemalloc.start()
load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_TOKEN')

class MindsEyeBot(commands.Bot):
    def __init__(self, botToken):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix='=',
            intents=intents
        )
        self.flaskApp = Flask(__name__)
        self.setup_routes()

    def setup_routes(self):
        @self.flaskApp.route('/bot-mention', methods=['POST'])
        def triggerBotResponse():
            data = request.json
            chatLogger = self.get_cog("ChatLogger")
            if chatLogger:
                self.loop.create_task(chatLogger.automatedSendMessage("No comment."))
            return '', 204

    async def on_ready(self):
        print(f'{self.user} has connected to Discord!')
    
    async def setup_hook(self) -> None:
        print("Starting up...")
        print("Loading extensions...")
        await self._load_extensions()
        print("Syncing commands...")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(e)
        print("Launching Flask server...")
        Thread(target=self.flaskApp.run, kwargs={"port": 5000}).start()
        print("Connecting to discord...")


    async def _load_extensions(self) -> None:
        for extension in ("chatLogging", "playerTracking", "mrpTracking",):
            await self.load_extension(f"cogs.{extension}")

bot = MindsEyeBot(BOT_TOKEN)

@bot.event
async def on_guild_join(guild):
    async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add):
        print(f"Joined {guild.name}")

@bot.tree.command(name="ping", description="Check bot connection and latency.")
async def ping(interaction: discord.Interaction):
    delay = round(bot.latency * 1000)
    embed = discord.Embed(title="Pong!", description=f"Latency: {delay}ms", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

        
def main():
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()
import discord
from discord import app_commands
from discord.ext import commands
import tracemalloc
from dotenv import load_dotenv
import os
from flask import Flask, request
from threading import Thread
from pymongo import MongoClient
import json
import asyncio
import time

tracemalloc.start()
load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
mongodbURI = "mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
mongoDBClient = MongoClient(mongodbURI) # sets up database client

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
        self.throttleInterval = 1
        self.lock = asyncio.Lock()
        self.newAccountTasks = []
        self.callsignChangeTasks = []

    def loadConfig(self):
        with open("config.json") as f:
            return json.load(f)

    def setup_routes(self):
        @self.flaskApp.route('/bot-mention', methods=['POST'])
        def triggerBotResponse():
            data = request.json
            chatLogger = self.get_cog("ChatLogger")
            if chatLogger:
                self.loop.create_task(chatLogger.automatedSendMessage("No comment."))
            return '', 204
        
        @self.flaskApp.route('/new-account', methods=['POST'])
        def triggerNewAccount():
            data = request.json
            db = mongoDBClient["OspreyEyes"]
            collection = db["configurations"]
            configuration = collection.find_one()
            if configuration["newAccountLogChannel"] == None:
                return 'New account log channel is not set.', 500
            if configuration["displayNewAccounts"] == False:
                for task in self.newAccountTasks:
                    task.cancel()
                self.newAccountTasks = [task for task in self.newAccountTasks if not task.cancelled()]
            channel = self.get_channel(int(configuration["newAccountLogChannel"]))
            async def sendMessage(embed, channel):
                async with self.lock:
                    await channel.send(embed=embed)
                    await asyncio.sleep(self.throttleInterval)
            embed = discord.Embed(
                title="New Account",
                description=f"Acoount ID: {data['acid']}\n Callsign: {data['callsign']}",
                color=discord.Color.green()
            )
            if configuration["displayNewAccounts"]:
                task = self.loop.create_task(sendMessage(embed, channel))
                self.newAccountTasks.append(task)
            return '', 204
    
        @self.flaskApp.route('/callsign-change', methods=['POST'])
        def triggerCallsignChange():
            data = request.json
            db = mongoDBClient["OspreyEyes"]
            collection = db["configurations"]
            configuration = collection.find_one()
            if configuration["callsignChangeLogChannel"] == None:
                return 'Callsign change log channel is not set.', 500
            if configuration["displayCallsignChanges"] == False:
                for task in self.callsignChangeTasks:
                    task.cancel()
                self.callsignChangeTasks = [task for task in self.callsignChangeTasks if not task.cancelled()]
            channel = self.get_channel(int(configuration["callsignChangeLogChannel"]))
            async def sendMessage(embed, channel):
                async with self.lock:
                    await channel.send(embed=embed)
                    await asyncio.sleep(self.throttleInterval)
            embed = discord.Embed(
                title="Callsign Change",
                description=f"Acoount ID: {data['acid']}\n Old Callsign: {data['oldCallsign']}\n New Callsign: {data['newCallsign']}",
                color=discord.Color.green()
            )
            if configuration["displayCallsignChanges"]:
                task = self.loop.create_task(sendMessage(embed, channel))
                self.callsignChangeTasks.append(task)
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
        self.config = self.loadConfig()
        print("Launching Flask server...")
        Thread(target=self.flaskApp.run, kwargs={"host": self.config["flaskHost"], "port": self.config["flaskPort"]}).start()
        print("Connecting to discord...")


    async def _load_extensions(self) -> None:
        for extension in ("chatLogging", "playerTracking", "mrpTracking", "config",):
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
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
import logging
import sys

load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
DATABASE_NAME = os.getenv('DATABASE_NAME')
mongodbURI = f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
mongoDBClient = MongoClient(mongodbURI) # sets up database client

class MindsEyeBot(commands.Bot):
    def __init__(self, botToken):
        # sets up logger
        self.logger = logging.getLogger("OSPREY EYES")
        self.logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        self.logger.addHandler(console_handler)

        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='=', intents=intents)

        self.flaskApp = Flask(__name__)
        self.throttleInterval = 0.2
        self.task_queue = asyncio.Queue()

        self.lock = asyncio.Lock()
        self.config = self.load_config()
        self.setup_routes()

        self.loop.create_task(self.process_tasks())

    def load_config(self):
        return mongoDBClient[DATABASE_NAME]["configurations"].find_one()

    async def on_ready(self):
        self.logger.log(20, f'{self.user} has connected to Discord!')
    
    async def setup_hook(self) -> None:
        self.logger.log(20, "Starting up...")
        self.logger.log(20, "Loading extensions...")
        await self._load_extensions()
        self.logger.log(20, "Syncing commands...")
        try:
            synced = await self.tree.sync()
            self.logger.log(20, f"Synced {len(synced)} command(s)")
        except Exception as e:
            self.logger.log(40, f"Exception while syncing commands. Error: {e}")

        self.logger.log(20, "Launching Flask server...")
        Thread(target=self.flaskApp.run, kwargs={"host": "127.0.0.1", "port": 5001}).start()
        self.logger.log(20, "Connecting to discord...")

    def setup_routes(self):
        @self.flaskApp.route("/bot-mention", methods=["POST"])
        def bot_mention(self):
            self.loop.create_task(self.get_cog("chatLogging").automatedSendMessage("Nothing can hide from the all seeing eye."))
            return "", 204
        @self.flaskApp.route("/aircraft-change", methods=["POST"])
        def aircraft_change(self):
            data = request.json
            if not isinstance(data, list):
                return 'Invalid data format. Expected a list.', 400
            
            channel = self.get_channel_config("aircraft-change")
            if not channel:
                return 'Aircraft change log channel is not set.', 500
            
            if not self.config["displayAircraftChanges"]:
                self.clear_tasks("aircraft-change")
                return "", 204

            embeds = [
                discord.Embed(
                    title="Aircraft Change",
                    description=f"Callsign: {change_data['callsign']}\n Old Aircraft: {change_data['oldAircraft']}\n New Aircraft: {change_data['newAircraft']}",
                    color=discord.Color.green()
                )
                for change_data in data
            ]
            task = self.loop.create_task(self.send_embeds(channel, embeds))
            self.add_task("aircraft-change", task)
            return "", 204
    
        @self.flaskApp.route("/new-account", methods=["POST"])
        def new_account(self):
            data = request.json
            if not isinstance(data, list):
                return 'Invalid data format. Expected a list.', 400
            
            channel = self.get_channel_config("new-account")
            if not channel:
                return 'New account log channel is not set.', 500
            
            if not self.config["displayNewAccounts"]:
                self.clear_tasks("new-account")
                return "", 204
            
            embeds = [
                discord.Embed(
                    title="New Account",
                    description=f"Acoount ID: {account_data['acid']}\n Callsign: {account_data['callsign']}",
                    color=discord.Color.green()
                )
                for account_data in data
            ]
            task = self.loop.create_task(self.send_embeds(channel, embeds))
            self.add_task("new-account", task)
            return "", 204
    
        @self.flaskApp.route("/callsign-change", methods=["POST"])
        def callsign_change(self):
            data = request.json
            if not isinstance(data, list):
                return 'Invalid data format. Expected a list.', 400
            
            channel = self.get_channel_config("callsign-change")
            if not channel:
                return 'Callsign change log channel is not set.', 500
            
            if not self.config["displayCallsignChanges"]:
                self.clear_tasks("callsign-change")
                return "", 204
            
            embeds = [
                discord.Embed(
                    title="Callsign Change",
                    description=f"Acoount ID: {callsign_data['acid']}\n Old Callsign: {callsign_data['oldCallsign']}\n New Callsign: {callsign_data['newCallsign']}",
                    color=discord.Color.green()
                )
                for callsign_data in data
            ]
            task = self.loop.create_task(self.send_embeds(channel, embeds))
            self.add_task("callsign-change", task)
            return "", 204
        
    
    async def send_embeds(self, channel, embeds):
        channel_id = self.config.get("log")
        async with self.lock:
            for embed in embeds:
                await channel.send(embed=embed)
                await asyncio.sleep(self.throttleInterval)

    def get_channel_config(self, event_type):
        if event_type == "aircraft-change":
            return self.get_channel(self.config["aircraftChangeLogChannel"])
        elif event_type == "new-account":
            return self.get_channel(self.config["newAccountLogChannel"])
        elif event_type == "callsign-change":
            return self.get_channel(self.config["callsignChangeLogChannel"])
        else:
            self.logger.log(40, f"Invalid event type: {event_type}")
    
    def add_task(self, task_type, task):
        self.task_lists[task_type].append(task)
        self.task_lists[task_type] = [t for t in self.task_lists[task_type] if not t.done()]

    def clear_tasks(self, task_type):
        for task in self.task_lists[task_type]:
            task.cancel()
        self.task_lists[task_type] = []

    async def _load_extensions(self) -> None:
        for extension in ("chatLogging", "playerTracking", "mrpTracking", "config",):
            await self.load_extension(f"cogs.{extension}")

bot = MindsEyeBot(BOT_TOKEN)

@bot.event
async def on_guild_join(guild):
    async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add):
        bot.logger.log(20, f"Joined {guild.name}")

@bot.tree.command(name="ping", description="Check bot connection and latency.")
async def ping(interaction: discord.Interaction):
    delay = round(bot.latency * 1000)
    embed = discord.Embed(title="Pong!", description=f"Latency: {delay}ms", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

def main():
    bot.run(BOT_TOKEN)

if __name__ == "__main__":
    main()
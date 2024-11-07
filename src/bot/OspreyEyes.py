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
import logging
import sys

tracemalloc.start()
load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
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
        super().__init__(
            command_prefix='=',
            intents=intents
        )
        self.DATBASE_NAME = os.getenv('DATABASE_NAME')
        self.flaskApp = Flask(__name__)
        self.setup_routes()
        self.throttleInterval = 0.2
        self.lock = asyncio.Lock()
        self.newAccountTasks = []
        self.callsignChangeTasks = []
        self.aircraftChangeTasks = []

    def loadConfig(self):
        with open("config.json") as f:
            return json.load(f)

    def setup_routes(self):
        @self.flaskApp.route('/bot-mention', methods=['POST'])
        def triggerBotResponse():
            data = request.json
            chatLogger = self.get_cog("ChatLogger")
            if chatLogger:
                self.loop.create_task(chatLogger.automatedSendMessage("Nothing can hide from the all seeing eye."))
            return '', 204
        
        @self.flaskApp.route('/aircraft-change', methods=['POST'])
        def triggerAircraftChange():
            data = request.json
            if not isinstance(data, list):
                return 'Invalid data format. Expected a list.', 400
            db = mongoDBClient[self.DATBASE_NAME]
            collection = db["configurations"]
            configuration = collection.find_one()
            if configuration["aircraftChangeLogChannel"] == None:
                return 'Aircraft change log channel is not set.', 500

            channel = self.get_channel(int(configuration["aircraftChangeLogChannel"]))
            async def sendMessages(channel, embeds):
                async with self.lock:
                    for embed in embeds:
                        await channel.send(embed=embed)
                        await asyncio.sleep(self.throttleInterval)
            embeds = []
            for change_data in data:
                embed = discord.Embed(
                    title="Aircraft Change",
                    description=f"Callsign: {change_data['callsign']}\n Old Aircraft: {change_data['oldAircraft']}\n New Aircraft: {change_data['newAircraft']}",
                    color=discord.Color.green()
                )
                embeds.append(embed)

            task = self.loop.create_task(sendMessages(channel, embeds))
            self.aircraftChangeTasks.append(task)
            return '', 204
        
        @self.flaskApp.route('/new-account', methods=['POST'])
        def triggerNewAccount():
            data = request.json
            if not isinstance(data, list):
                return 'Invalid data format. Expected a list.', 400
            
            db = mongoDBClient[self.DATBASE_NAME]
            collection = db["configurations"]
            configuration = collection.find_one()
            if configuration["newAccountLogChannel"] == None:
                return 'New account log channel is not set.', 500
            if configuration["displayNewAccounts"] == False:
                for task in self.newAccountTasks:
                    task.cancel()
                self.newAccountTasks = [task for task in self.newAccountTasks if not task.cancelled()]
            channel = self.get_channel(int(configuration["newAccountLogChannel"]))

            async def sendMessages(channel, embeds):
                async with self.lock:
                    for embed in embeds:
                        await channel.send(embed=embed)
                        await asyncio.sleep(self.throttleInterval)

            embeds = []
            for account_data in data:
                embed = discord.Embed(
                    title="New Account",
                    description=f"Acoount ID: {account_data['acid']}\n Callsign: {account_data['callsign']}",
                    color=discord.Color.green()
                )
                embeds.append(embed)


            if configuration["displayNewAccounts"]:
                task = self.loop.create_task(sendMessages(channel, embeds))
                self.newAccountTasks.append(task)
            return '', 204
    
        @self.flaskApp.route('/callsign-change', methods=['POST'])
        def triggerCallsignChange():
            data = request.json
            if not isinstance(data, list):
                return 'Invalid data format. Expected a list.', 400

            db = mongoDBClient[self.DATBASE_NAME]
            collection = db["configurations"]
            configuration = collection.find_one()
            if configuration["callsignChangeLogChannel"] == None:
                return 'Callsign change log channel is not set.', 500
            if configuration["displayCallsignChanges"] == False:
                for task in self.callsignChangeTasks:
                    task.cancel()
                self.callsignChangeTasks = [task for task in self.callsignChangeTasks if not task.cancelled()]
            channel = self.get_channel(int(configuration["callsignChangeLogChannel"]))
            async def sendMessages(channel, embeds):
                async with self.lock:
                    for embed in embeds:
                        await channel.send(embed=embed)
                        await asyncio.sleep(self.throttleInterval)
            embeds = []
            for change_data in data:
                embed = discord.Embed(
                    title="Callsign Change",
                    description=f"Acoount ID: {change_data['acid']}\n Old Callsign: {change_data['oldCallsign']}\n New Callsign: {change_data['newCallsign']}",
                    color=discord.Color.green()
                )
                embeds.append(embed)
            if configuration["displayCallsignChanges"]:
                task = self.loop.create_task(sendMessages(channel, embeds))
                self.callsignChangeTasks.append(task)
            return '', 204
            

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
        self.config = self.loadConfig()
        self.logger.log(20, "Launching Flask server...")
        Thread(target=self.flaskApp.run, kwargs={"host": self.config["flaskHost"], "port": self.config["flaskPort"]}).start()
        self.logger.log(20, "Connecting to discord...")


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
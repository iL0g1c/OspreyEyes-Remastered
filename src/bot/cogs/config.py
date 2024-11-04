import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
from motor.motor_asyncio import AsyncIOMotorClient
from MindsEye import MindsEyeBot

class Config(commands.Cog):
    def __init__(self):
        load_dotenv()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = "mongodb://adminUser:password@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongoDBClient = AsyncIOMotorClient(mongodbURI) # sets up database client

    
    configGroup = app_commands.Group(name="config", description="Commands for configuring the bot.") # creates the config commands group

    @configGroup.command(name="set_callsign_log_channel", description="Set the channel for callsign change logs.")
    async def setCallsignLogChannel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for callsign change logs
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"callsignLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set callsignLogChannel to {channel.mention}")

    @configGroup.command(name="toggle_display_callsign_changes", description="Toggle the discord displaying of callsign changes.")
    async def toggleCallsignChanges(self, interaction: discord.Interaction): # toggles the discord displaying of callsign changes
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["displayCallsignChanges"]
        await collection.update_one({}, {"$set": {"displayCallsignChanges": newConfiguration}})
        await interaction.response.send_message(f"Set displayCallsignChanges to {newConfiguration}")
    

    @configGroup.command(name="toggle_display_new_accounts", description="Toggle logging new geofs accounts in the callsign log channel.")
    async def toggleNewAccounts(self, interaction: discord.Interaction): # toggles logging new geofs accounts in the callsign log channel
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["displayNewAccounts"]
        await collection.update_one({}, {"$set": {"displayNewAccounts": newConfiguration}})
        await interaction.response.send_message(f"Set displayNewAccounts to {newConfiguration}")

    @configGroup.command(name="toggle_user_count_logger", description="Set the channel for callsign change logs.")
    async def toggleUserCountLogger(self, interaction: discord.Interaction): # toggles the user count logger
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["countUsers"]
        await collection.update_one({}, {"$set": {"countUsers": newConfiguration}})
        await interaction.response.send_message(f"Set userCountLogger to {newConfiguration}")

    
    @configGroup.command(name="toggle_chat_message_logging", description="Toggle the logging of chat messages.")
    async def toggleChatMessageLogging(self, interaction: discord.Interaction): # toggles the logging of chat messages
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["saveChatMessages"]
        await collection.update_one({}, {"$set": {"saveChatMessages": newConfiguration}})
        await interaction.response.send_message(f"Set saveChatMessages to {newConfiguration}")

    @configGroup.command(name="toggle_heatmap_cumulation", description="Toggle the cumulation of player locations for the heatmap.")
    async def toggleHeatmapCumulation(self, interaction: discord.Interaction): # toggles the cumulation of player locations for the heatmap
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["accumulateHeatMap"]
        await collection.update_one({}, {"$set": {"accumulateHeatMap": newConfiguration}})
        await interaction.response.send_message(f"Set accumulateHeatMap to {newConfiguration}")

    
    @configGroup.command(name="toggle_user_tracking", description="Toggle the tracking of pilots on GeoFS.")
    async def togglePlayerLocationTracking(self, interaction: discord.Interaction): # toggles saving users to the database
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["storeUsers"]
        await collection.update_one({}, {"$set": {"storeUsers": newConfiguration}})
        await interaction.response.send_message(f"Set storeUsers to {newConfiguration}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(Config())
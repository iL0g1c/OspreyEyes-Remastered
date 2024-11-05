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
        self.DATABASE_NAME = os.getenv('DATABASE_NAME')
        mongodbURI = f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongoDBClient = AsyncIOMotorClient(mongodbURI) # sets up database client

    
    configGroup = app_commands.Group(name="config", description="Commands for configuring the bot.") # creates the config commands group
    
    @configGroup.command(name="display_configs", description="Display the current bot configurations.")
    async def displayConfigs(self, interaction: discord.Interaction):
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        embed = discord.Embed(
            title="Current Configurations", 
            description=(
                f"Display Callsign Changes: {configuration['displayCallsignChanges']}\n" +
                f"Display New Accounts: {configuration['displayNewAccounts']}\n" +
                f"User Count Logger: {configuration['countUsers']}\n" +
                f"Chat Message Logging: {configuration['saveChatMessages']}\n" +
                f"Heatmap Cumulation: {configuration['accumulateHeatMap']}\n" +
                f"User Tracking: {configuration['storeUsers']}\n" +
                f"Aircraft Distribution: {configuration['logAircraftDistributions']}\n" +
                f"Callsign Change Log Channel: <#{configuration['callsignChangeLogChannel']}>\n" +
                f"New Account Log Channel: <#{configuration['newAccountLogChannel']}>\n" +
                f"Aircraft Change Log Channel: <#{configuration['aircraftChangeLogChannel']}>\n" + 
                f"Aircraft Change Logging: {configuration['logAircraftChanges']}"
            ),
            color=discord.Color.greyple()
        )
        await interaction.response.send_message(embed=embed)

    toggleGroup = app_commands.Group(name="toggle", description="Toggle various bot features.")
    configGroup.add_command(toggleGroup)

    @toggleGroup.command(name="display_callsign_changes", description="Toggle the discord displaying of callsign changes.")
    async def toggleCallsignChanges(self, interaction: discord.Interaction): # toggles the discord displaying of callsign changes
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["displayCallsignChanges"]
        await collection.update_one({}, {"$set": {"displayCallsignChanges": newConfiguration}})
        await interaction.response.send_message(f"Set displayCallsignChanges to {newConfiguration}")
    
    @toggleGroup.command(name="display_new_accounts", description="Toggle logging new geofs accounts in the callsign log channel.")
    async def toggleNewAccounts(self, interaction: discord.Interaction): # toggles logging new geofs accounts in the callsign log channel
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["displayNewAccounts"]
        await collection.update_one({}, {"$set": {"displayNewAccounts": newConfiguration}})
        await interaction.response.send_message(f"Set displayNewAccounts to {newConfiguration}")

    @toggleGroup.command(name="user_count_logger", description="Set the channel for callsign change logs.")
    async def toggleUserCountLogger(self, interaction: discord.Interaction): # toggles the user count logger
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["countUsers"]
        await collection.update_one({}, {"$set": {"countUsers": newConfiguration}})
        await interaction.response.send_message(f"Set userCountLogger to {newConfiguration}")

    @toggleGroup.command(name="chat_message_logging", description="Toggle the logging of chat messages.")
    async def toggleChatMessageLogging(self, interaction: discord.Interaction): # toggles the logging of chat messages
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["saveChatMessages"]
        await collection.update_one({}, {"$set": {"saveChatMessages": newConfiguration}})
        await interaction.response.send_message(f"Set saveChatMessages to {newConfiguration}")

    @toggleGroup.command(name="heatmap_cumulation", description="Toggle the cumulation of player locations for the heatmap.")
    async def toggleHeatmapCumulation(self, interaction: discord.Interaction): # toggles the cumulation of player locations for the heatmap
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["accumulateHeatMap"]
        await collection.update_one({}, {"$set": {"accumulateHeatMap": newConfiguration}})
        await interaction.response.send_message(f"Set accumulateHeatMap to {newConfiguration}")

    
    @toggleGroup.command(name="user_tracking", description="Toggle the tracking of pilots on GeoFS.")
    async def togglePlayerLocationTracking(self, interaction: discord.Interaction): # toggles saving users to the database
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["storeUsers"]
        await collection.update_one({}, {"$set": {"storeUsers": newConfiguration}})
        await interaction.response.send_message(f"Set storeUsers to {newConfiguration}")
    
    @toggleGroup.command(name="aircraft_distribution", description="Toggle the logging of aircraft distributions.")
    async def toggleAircraftDistributions(self, interaction: discord.Interaction): # toggles the logging of aircraft distributions
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["logAircraftDistributions"]
        await collection.update_one({}, {"$set": {"logAircraftDistributions": newConfiguration}})
        await interaction.response.send_message(f"Set logAircraftDistributions to {newConfiguration}")

    @toggleGroup.command(name="aircraft_change_logging", description="Toggle the logging of aircraft changes.")
    async def toggleAircraftChangeLogging(self, interaction: discord.Interaction): # toggles the logging of aircraft changes
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["logAircraftChanges"]
        await collection.update_one({}, {"$set": {"logAircraftChanges": newConfiguration}})
        await interaction.response.send_message(f"Set logAircraftChanges to {newConfiguration}")

    setGroup = app_commands.Group(name="set", description="Set various bot parameters.") # creates the set commands group
    configGroup.add_command(setGroup) # adds the set commands group to the config commands group

    @setGroup.command(name="callsign_change_log_channel", description="Set the channel for callsign change logs.")
    async def setCallsignChangeLogChannel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for callsign change logs
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"callsignChangeLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set callsignChangeLogChannel to {channel.mention}")
    
    @setGroup.command(name="new_account_log_channel", description="Set the channel for new account logs.")
    async def setNewAccountLogChannel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for new account logs
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"newAccountLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set newAccountLogChannel to {channel.mention}")

    @setGroup.command(name="aircraft_change_log_channel", description="Set the channel logging when a pilot changes their aircraft")
    async def setAircraftChangeLogChannel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for aircraft change logs
        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"aircraftChangeLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set aircraftChangeLogChannel to {channel.mention}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(Config())
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
from motor.motor_asyncio import AsyncIOMotorClient
from OspreyEyes import MindsEyeBot

class Config(commands.Cog):
    def __init__(self):
        load_dotenv()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME')
        mongodbURI = f"mongodb://OspreyEyes:{DATABASE_TOKEN}@192.168.1.132:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=OspreyEyes"
        self.mongo_db_client = AsyncIOMotorClient(mongodbURI) # sets up database client

    
    config_group = app_commands.Group(name="config", description="Commands for configuring the bot.") # creates the config commands group
    
    @config_group.command(name="display_configs", description="Display the current bot configurations.")
    async def display_configs(self, interaction: discord.Interaction):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        embed = discord.Embed(
            title="Current Configurations", 
            description=(
                f"Chat Message Logging: {configuration['saveChatMessages']}\n" +
                f"Heatmap Cumulation: {configuration['accumulateHeatMap']}\n" +
                f"User Tracking: {configuration['storeUsers']}\n" +
                f"Callsign Change Log Channel: <#{configuration['callsignChangeLogChannel']}>\n" +
                f"New Account Log Channel: <#{configuration['newAccountLogChannel']}>\n" +
                f"Aircraft Change Log Channel: <#{configuration['aircraftChangeLogChannel']}>\n" + 
                f"Display Callsign Changes: {configuration['displayCallsignChanges']}\n" +
                f"Display New Accounts: {configuration['displayNewAccounts']}\n" +
                f"Display Aircraft Changes: {configuration['displayAircraftChanges']}\n" +
                f"User Count Logger: {configuration['countUsers']}\n" +
                f"Aircraft Distribution: {configuration['logAircraftDistributions']}\n" +
                f"Aircraft Change Logging: {configuration['logAircraftChanges']}\n" +
                f"MRP Activity Tracking: {configuration['logMRPActivity']}"

            ),
            color=discord.Color.greyple()
        )
        await interaction.response.send_message(embed=embed)

    toggle_group = app_commands.Group(name="toggle", description="Toggle various bot features.")
    config_group.add_command(toggle_group)

    @toggle_group.command(name="activity_tracking", description="Toggle the tracking of MRP activity.")
    async def mrp_activity_tracker(self, interaction: discord.Interaction): # toggles the tracking of MRP activity
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["logMRPActivity"]
        await collection.update_one({}, {"$set": {"logMRPActivity": new_configuration}})
        await interaction.response.send_message(f"Set logMRPActivity to {new_configuration}")

    @toggle_group.command(name="display_callsign_changes", description="Toggle the discord displaying of callsign changes.")
    async def toggle_callsign_change_tracking(self, interaction: discord.Interaction): # toggles the discord displaying of callsign changes
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["displayCallsignChanges"]
        await collection.update_one({}, {"$set": {"displayCallsignChanges": new_configuration}})
        await interaction.response.send_message(f"Set displayCallsignChanges to {new_configuration}")
    
    @toggle_group.command(name="display_new_accounts", description="Toggle logging new geofs accounts in the callsign log channel.")
    async def display_new_accounts(self, interaction: discord.Interaction): # toggles logging new geofs accounts in the callsign log channel
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["displayNewAccounts"]
        await collection.update_one({}, {"$set": {"displayNewAccounts": new_configuration}})
        await interaction.response.send_message(f"Set displayNewAccounts to {new_configuration}")

    @toggle_group.command(name="display_aircraft_changes", description="Toggle the discord displaying of aircraft changes.")
    async def display_aircraft_changes(self, interaction: discord.Interaction): # toggles the discord displaying of aircraft changes
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["displayAircraftChanges"]
        await collection.update_one({}, {"$set": {"displayAircraftChanges": new_configuration}})
        await interaction.response.send_message(f"Set displayAircraftChanges to {new_configuration}")

    @toggle_group.command(name="user_count_logger", description="Set the channel for callsign change logs.")
    async def toggle_user_count_logger(self, interaction: discord.Interaction): # toggles the user count logger
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["countUsers"]
        await collection.update_one({}, {"$set": {"countUsers": new_configuration}})
        await interaction.response.send_message(f"Set userCountLogger to {new_configuration}")

    @toggle_group.command(name="chat_message_logging", description="Toggle the logging of chat messages.")
    async def toggle_chat_message_logging(self, interaction: discord.Interaction): # toggles the logging of chat messages
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["saveChatMessages"]
        await collection.update_one({}, {"$set": {"saveChatMessages": new_configuration}})
        await interaction.response.send_message(f"Set saveChatMessages to {new_configuration}")

    @toggle_group.command(name="heatmap_cumulation", description="Toggle the cumulation of player locations for the heatmap.")
    async def toggle_heat_map_cumulation(self, interaction: discord.Interaction): # toggles the cumulation of player locations for the heatmap
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["accumulateHeatMap"]
        await collection.update_one({}, {"$set": {"accumulateHeatMap": new_configuration}})
        await interaction.response.send_message(f"Set accumulateHeatMap to {new_configuration}")

    
    @toggle_group.command(name="user_tracking", description="Toggle the tracking of pilots on GeoFS.")
    async def toggle_user_tracking(self, interaction: discord.Interaction): # toggles saving users to the database
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["storeUsers"]
        await collection.update_one({}, {"$set": {"storeUsers": new_configuration}})
        await interaction.response.send_message(f"Set storeUsers to {new_configuration}")
    
    @toggle_group.command(name="aircraft_distribution", description="Toggle the logging of aircraft distributions.")
    async def toggle_aircraft_distributions(self, interaction: discord.Interaction): # toggles the logging of aircraft distributions
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["logAircraftDistributions"]
        await collection.update_one({}, {"$set": {"logAircraftDistributions": new_configuration}})
        await interaction.response.send_message(f"Set logAircraftDistributions to {new_configuration}")

    @toggle_group.command(name="aircraft_change_logging", description="Toggle the logging of aircraft changes.")
    async def toggle_aircraft_change_logging(self, interaction: discord.Interaction): # toggles the logging of aircraft changes
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        configuration = await collection.find_one()
        new_configuration = not configuration["logAircraftChanges"]
        await collection.update_one({}, {"$set": {"logAircraftChanges": new_configuration}})
        await interaction.response.send_message(f"Set logAircraftChanges to {new_configuration}")

    setGroup = app_commands.Group(name="set", description="Set various bot parameters.") # creates the set commands group
    config_group.add_command(setGroup) # adds the set commands group to the config commands group

    @setGroup.command(name="callsign_change_log_channel", description="Set the channel for callsign change logs.")
    async def set_callsign_change_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for callsign change logs
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"callsignChangeLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set callsignChangeLogChannel to {channel.mention}")
    
    @setGroup.command(name="new_account_log_channel", description="Set the channel for new account logs.")
    async def set_new_Account_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for new account logs
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"newAccountLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set newAccountLogChannel to {channel.mention}")

    @setGroup.command(name="aircraft_change_log_channel", description="Set the channel logging when a pilot changes their aircraft")
    async def set_aircraft_change_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel): # sets the channel for aircraft change logs
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["configurations"]
        await collection.update_one({}, {"$set": {"aircraftChangeLogChannel": channel.id}}, upsert=True)
        await interaction.response.send_message(f"Set aircraftChangeLogChannel to {channel.mention}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(Config())
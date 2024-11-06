import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from MindsEye import MindsEyeBot
from paginationEmbed import PaginatedEmbed

class MRPTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        load_dotenv()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME')
        MONGO_DB_URI = f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongo_db_client = AsyncIOMotorClient(MONGO_DB_URI)

    mrp_group = app_commands.Group(name="mrp", description="Commands for the MRP tracker.")

    @mrp_group.command(name="add_force", description="Add a force to the MRP tracker.")
    async def addForce(self, interaction: discord.Interaction, name: str, callsign_filter: str):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        await collection.insert_one({"callsign_filter": callsign_filter, "name": name, "patrols": []})
        await interaction.response.send_message(f"Force {name} added with callsign_filter {callsign_filter}")
    
    @mrp_group.command(name="remove_force", description="Remove a force from the MRP tracker.")
    async def removeForce(self, interaction: discord.Interaction, name: str):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        await collection.delete_one({"name": name})
        await interaction.response.send_message(f"Force with name {name} removed.")
    
    @mrp_group.command(name="get_forces", description="Get all forces in the MRP tracker.")
    async def getForces(self, interaction: discord.Interaction):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        forces = await collection.find().to_list(length=None)
        forceList = []
        for force in forces:
            forceList.append(f"Name: {force['name']}, Callsign Filter: {force['callsign_filter']}")
        embed = PaginatedEmbed(forceList, title="Forces", description="List of forces.")
        await interaction.response.send_message(embed=embed.embed, view=embed)

    @mrp_group.command(name="list_force_patrols", description="List all patrols for a force.")
    async def listForcePatrols(self, interaction: discord.Interaction, name: str):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        force = await collection.find_one({"name": name})
        patrolList = []
        for patrol in force["patrols"]:
            patrolList.append(f"Callsign: {patrol['callsign']}, Start Time: {patrol['start_time']}, End Time: {patrol['end_time']}")
        embed = PaginatedEmbed(patrolList, title="Patrols", description="List of patrols.")
        await interaction.response.send_message(embed=embed.embed, view=embed)

    @mrp_group.command(name="change_callsign_filter", description="Change the callsign_filter of a force.")
    async def changeCallsignFilter(self, interaction: discord.Interaction, name: str, new_callsign_filter: str):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        await collection.update_one({"name": name}, {"$set": {"callsign_filter": new_callsign_filter}})
        await interaction.response.send_message(f"Force {name} callsign_filter changed to {new_callsign_filter}")



    @mrp_group.command(name="get_total_patrol_hours", description="Get the total patrol hours for a force.")
    @app_commands.choices(time_span=[
        app_commands.Choice(name="before", value="before"),
        app_commands.Choice(name="after", value="after"),
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="all", value="all"),
    ])
    async def get_total_patrol_hours(self, interaction: discord.Interaction, name: str, time_span: app_commands.Choice[str], day: int, month: int, year: int):
        await interaction.response.defer()
        if not time_span.value == "all":
            try:
                targetDate = datetime(year, month, day)
            except ValueError:
                await interaction.response.send_message("Invalid date.")
                return
            
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        force = await collection.find_one({"name": name})
        total_hours = 0
        for patrol in force["patrols"]:
            if patrol["end_time"] != None:
                if time_span.value == "all":
                    total_hours += (patrol["end_time"] - patrol["start_time"]).total_seconds() / 3600
                elif time_span.value == "before":
                    if patrol["end_time"] < targetDate:
                        total_hours += (patrol["end_time"] - patrol["start_time"]).total_seconds() / 3600
                elif time_span.value == "after":
                    if[patrol["end_time"] > targetDate]:
                        total_hours += (patrol["end_time"] - patrol["start_time"]).total_seconds() / 3600
                elif time_span.value == "on":
                    if patrol["end_time"].date() == targetDate.date():
                        total_hours += (patrol["end_time"] - patrol["start_time"]).total_seconds() / 3600


        embed = discord.Embed(
            title=f"Total patrol hours for force {force['name']}",
            description=f"{round(total_hours, 2)} hours."
        )
        await interaction.followup.send(embed=embed)

async def setup(bot: MindsEyeBot):
    await bot.add_cog(MRPTracker(bot))
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import os
from motor.motor_asyncio import AsyncIOMotorClient
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



    @app_commands.command(name="add_force", description="Add a force to the MRP tracker.")
    async def addForce(self, interaction: discord.Interaction, identifier: str, name: str):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        await collection.insert_one({"identifier": identifier, "name": name})
        await interaction.response.send_message(f"Force {name} added with identifier {identifier}")
    
    @app_commands.command(name="remove_force", description="Remove a force from the MRP tracker.")
    async def removeForce(self, interaction: discord.Interaction, identifier: str):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        await collection.delete_one({"identifier": identifier})
        await interaction.response.send_message(f"Force with identifier {identifier} removed.")
    
    @app_commands.command(name="get_forces", description="Get all forces in the MRP tracker.")
    async def getForces(self, interaction: discord.Interaction):
        db = self.mongo_db_client[self.DATABASE_NAME]
        collection = db["forces"]
        forces = await collection.find().to_list(length=None)
        forceList = []
        for force in forces:
            forceList.append(f"Identifier: {force['identifier']}, Name: {force['name']}")
        embed = PaginatedEmbed(forceList, title="Forces", description="List of forces.")
        await interaction.response.send_message(embed=embed.embed, view=embed)
        

async def setup(bot: MindsEyeBot):
    await bot.add_cog(MRPTracker(bot))
import discord
from discord import app_commands
from discord.ext import commands
from MindsEye import MindsEyeBot
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

class ChatLogger(commands.Cog):
    def __init__(self, bot):
        load_dotenv()
        self.bot = bot
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongodbClient = AsyncIOMotorClient(mongodbURI)

    chatGroup = app_commands.Group(name="chat", description="Commands for logging chat messages.")

    @chatGroup.command(name="send_chat_message", description="Send a chat message to the geofs chat.")
    async def sendChatMessage(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer()
        self.multiplayerAPI.sendMsg(message)
        await interaction.followup.send(f"Sent message: {message}")

    @chatGroup.command(name="toggle_chat_message_logging", description="Toggle the logging of chat messages.")
    async def toggleChatMessageLogging(self, interaction: discord.Interaction):
        db = self.mongodbClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = collection.find_one()
        newConfiguration = not configuration["saveChatMessages"]
        collection.update_one({}, {"$set": {"saveChatMessages": newConfiguration}})
        await interaction.response.send_message(f"Set saveChatMessages to {newConfiguration}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(ChatLogger(bot))
import discord
from discord import app_commands
from discord.ext import commands
from multiplayerAPI import MultiplayerAPI
from MindsEye import MindsEyeBot
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from urllib.parse import unquote

class ChatLogger(commands.Cog):
    def __init__(self, bot):
        load_dotenv()
        self.bot = bot
        self.sessionID = os.getenv('GEOFS_SESSION_ID')
        self.accountID = os.getenv('GEOFS_ACCOUNT_ID')
        self.multiplayerAPI = MultiplayerAPI(self.sessionID, self.accountID)
        self.multiplayerAPI.handshake()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = "mongodb://adminUser:password@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongodbClient = AsyncIOMotorClient(mongodbURI)

    @app_commands.command(name="get_chat_messages", description="Get the chat messages from the multiplayer API.")
    async def getChatMessages(self, interaction: discord.Interaction):
        chat_messages = [
            {**message, "msg": unquote(message["msg"])}
            for message in self.multiplayerAPI.getMessages()
        ]

        await interaction.response.send_message(
            chat_messages if chat_messages else "No chat messages."
        )

async def setup(bot: MindsEyeBot):
    await bot.add_cog(ChatLogger(bot))
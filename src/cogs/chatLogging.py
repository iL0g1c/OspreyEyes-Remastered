import discord
from discord import app_commands
from discord.ext import commands, tasks
from multiplayerAPI import MultiplayerAPI
from MindsEye import MindsEyeBot
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from urllib.parse import unquote
from datetime import datetime

class ChatLogger(commands.Cog):
    def __init__(self, bot):
        load_dotenv()
        self.bot = bot
        self.sessionID = os.getenv('GEOFS_SESSION_ID')
        self.accountID = os.getenv('GEOFS_ACCOUNT_ID')
        self.multiplayerAPI = MultiplayerAPI(self.sessionID, self.accountID)
        self.multiplayerAPI.handshake()
        self.currentChatMessages = []
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = "mongodb://adminUser:password@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongodbClient = AsyncIOMotorClient(mongodbURI)
        print("Starting multiplayer server heartbeat...")
        self.fetchChatMessages.start()

    @tasks.loop(seconds=1)
    async def fetchChatMessages(self):
        self.currentChatMessages = [
            {**message, "msg": unquote(message["msg"]), "datetime": datetime.now()}
            for message in self.multiplayerAPI.getMessages()
        ]
        if self.currentChatMessages:
            db = self.mongodbClient["OspreyEyes"]
            collection = db["chat_messages"]
            await collection.insert_many(self.currentChatMessages)

    chatGroup = app_commands.Group(name="chat", description="Commands for logging chat messages.")

    @chatGroup.command(name="send_chat_message", description="Send a chat message to the geofs chat.")
    async def sendChatMessage(self, interaction: discord.Interaction, message: str):
        print(1)
        await interaction.response.defer()
        self.multiplayerAPI.sendMsg(message)
        await interaction.followup.send(f"Sent message: {message}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(ChatLogger(bot))
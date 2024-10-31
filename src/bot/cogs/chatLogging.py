import discord
from discord import app_commands
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys
from dotenv import load_dotenv
from MindsEye import MindsEyeBot


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared import multiplayerAPI

class ChatLogger(commands.Cog):
    def __init__(self, bot):
        # gets envs
        load_dotenv()
        self.bot = bot
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        SESSION_ID = os.getenv('GEOFS_SESSION_ID')
        ACCOUNT_ID = os.getenv('GEOFS_ACCOUNT_ID')
        mongodbURI = f"mongodb://adminUser:{DATABASE_TOKEN}@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongoDBClient = AsyncIOMotorClient(mongodbURI) # sets up database client
        self.multiplayerAPI = multiplayerAPI.MultiplayerAPI(SESSION_ID, ACCOUNT_ID) # sets up multiplayer API

    chatGroup = app_commands.Group(name="chat", description="Commands for logging chat messages.") # sets up command group

    async def automatedSendMessage(self, message):
        print("Sending message.")
        self.multiplayerAPI.handshake()
        self.multiplayerAPI.sendMsg(message)

    @chatGroup.command(name="send_chat_message", description="Send a chat message to the geofs chat.")
    async def sendChatMessage(self, interaction: discord.Interaction, message: str): # sends a chat message to geofs chat
        await interaction.response.defer()
        self.multiplayerAPI.handshake()
        self.multiplayerAPI.sendMsg(message)
        await interaction.followup.send(f"Sent message: {message}")

    @chatGroup.command(name="toggle_chat_message_logging", description="Toggle the logging of chat messages.")
    async def toggleChatMessageLogging(self, interaction: discord.Interaction): # toggles the logging of chat messages
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["saveChatMessages"]
        await collection.update_one({}, {"$set": {"saveChatMessages": newConfiguration}})
        await interaction.response.send_message(f"Set saveChatMessages to {newConfiguration}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(ChatLogger(bot))
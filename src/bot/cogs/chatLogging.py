import discord
from discord import app_commands
from discord.ext import commands
import os
import sys
from dotenv import load_dotenv
from OspreyEyes import MindsEyeBot


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared import multiplayerAPI

class ChatLogger(commands.Cog):
    def __init__(self, bot):
        # gets envs
        load_dotenv()
        self.bot = bot
        SESSION_ID = os.getenv('GEOFS_SESSION_ID')
        ACCOUNT_ID = os.getenv('GEOFS_ACCOUNT_ID')
        self.multiplayerAPI = multiplayerAPI.MultiplayerAPI(SESSION_ID, ACCOUNT_ID) # sets up multiplayer API

    chatGroup = app_commands.Group(name="chat", description="Commands for logging chat messages.") # sets up command group

    async def automatedSendMessage(self, message):
        self.multiplayerAPI.handshake()
        self.multiplayerAPI.sendMsg(message)

    @chatGroup.command(name="send_chat_message", description="Send a chat message to the geofs chat.")
    async def sendChatMessage(self, interaction: discord.Interaction, message: str): # sends a chat message to geofs chat
        await interaction.response.defer()
        self.multiplayerAPI.handshake()
        self.multiplayerAPI.sendMsg(message)
        await interaction.followup.send(f"Sent message: {message}")

async def setup(bot: MindsEyeBot):
    await bot.add_cog(ChatLogger(bot))
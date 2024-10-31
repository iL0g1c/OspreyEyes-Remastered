import discord
from discord.ext import commands
from MindsEye import MindsEyeBot

class MRPTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

async def setup(bot: MindsEyeBot):
    await bot.add_cog(MRPTracker(bot))
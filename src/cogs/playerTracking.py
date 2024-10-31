import discord
from discord import app_commands
from discord.ext import commands
from MindsEye import MindsEyeBot
from mapAPI import MapAPI

class PlayerTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mapAPI = MapAPI()

    @app_commands.command(name="get_online_users", description="Get the online users from the map API.")
    async def getOnlineUsers(self, interaction: discord.Interaction):
        online_users = self.mapAPI.getUsers(False)
        for user in online_users:
            print(f"airspeed: {user.airspeed}\n userInfo: {user.userInfo}\n coordinates {user.coordinates}\n altitude: {user.altitude}\n verticalSpeed: {user.verticalSpeed}\n aircraft: {user.aircraft}")  
        # await interaction.response.send_message(
        #     online_users if online_users else "No online users."
        # )

async def setup(bot: MindsEyeBot):
    await bot.add_cog(PlayerTracker(bot))
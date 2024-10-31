import discord
from discord import app_commands
from discord.ext import commands
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import numpy as np
import io
from scipy.ndimage import gaussian_filter
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from MindsEye import MindsEyeBot
from paginationEmbed import PaginatedEmbed

class PlayerTracker(commands.Cog):
    def __init__(self, bot):
        load_dotenv()
        self.bot = bot
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = "mongodb://adminUser:password@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongodbClient = AsyncIOMotorClient(mongodbURI)

    playersGroup = app_commands.Group(name="players", description="Commands for tracking player activity.")

    @playersGroup.command(name="toggle_heatmap_cumulation", description="Toggle the cumulation of player locations for the heatmap.")
    async def toggleHeatmapCumulation(self, interaction: discord.Interaction):
        db = self.mongodbClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = collection.find_one()
        newConfiguration = not configuration["accumulateHeatMap"]
        collection.update_one({}, {"$set": {"accumulateHeatMap": newConfiguration}})
        await interaction.response.send_message(f"Set accumulateHeatMap to {newConfiguration}")
    
    @playersGroup.command(name="toggle_player_location_tracking", description="Toggle the tracking of player locations.")
    async def togglePlayerLocationTracking(self, interaction: discord.Interaction):
        db = self.mongodbClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = collection.find_one()
        newConfiguration = not configuration["fetchOnlineUsers"]
        collection.update_one({}, {"$set": {"fetchOnlineUsers": newConfiguration}})
        await interaction.response.send_message(f"Set fetchOnlineUsers to {newConfiguration}")

    @playersGroup.command(name="get_online_users", description="Get the online users from the map API.")
    async def getOnlineUsers(self, interaction: discord.Interaction):
        stringifiedUsers = []
        for user in self.currentOnlineUsers:
            stringifiedUsers.append(f"Callsign: {user.userInfo["callsign"]}, Account ID: {user.userInfo["id"]} Latitude: {user.coordinates[0]}, Longitude: {user.coordinates[1]} Aircraft: {user.aircraft["type"]}")
        embed = PaginatedEmbed(stringifiedUsers, title="Online Users", description="List of online users.")
        await interaction.response.send_message(embed=embed.embed, view=embed)


    @playersGroup.command(name="generate_player_heatmap", description="Generate a heatmap of player activity locations.")
    async def heatmap(self, interaction: discord.Interaction):
        await interaction.response.defer()

        db = self.mongodbClient["OspreyEyes"]
        collection = db["player_locations"]
        cursor = collection.find()
        data = await cursor.to_list(length=None)
        latitudes = [doc["latitude"] for doc in data]
        longitudes = [doc["longitude"] for doc in data]


        # set up the map
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw={"projection": ccrs.PlateCarree()})
        ax.coastlines()
        ax.set_global()
        ax.set_extent([-180, 180, -90, 90], crs=ccrs.PlateCarree())

        heatmap, xedges, yedges = np.histogram2d(
            longitudes,
            latitudes,
            bins=100,
            range=[[-180, 180], [-90, 90]],
        )

        heatmap = gaussian_filter(heatmap, sigma=1) # smoozes the colors

        extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
        ax.imshow(heatmap.T, extent=extent, origin="lower", cmap="viridis", alpha=0.6)

        # save the figure to a BytesIO object
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, dpi=150)
        buf.seek(0)

        await interaction.followup.send(file=discord.File(buf, "heatmap.png"))
        buf.close()

async def setup(bot: MindsEyeBot):
    await bot.add_cog(PlayerTracker(bot))
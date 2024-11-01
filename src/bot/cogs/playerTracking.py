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
import sys
from MindsEye import MindsEyeBot
from paginationEmbed import PaginatedEmbed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared import mapAPI

class PlayerTracker(commands.Cog):
    def __init__(self, bot):
        # gets envs
        load_dotenv()
        self.bot = bot
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        self.mapAPI = mapAPI.MapAPI()
        mongodbURI = "mongodb://adminUser:password@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongoDBClient = AsyncIOMotorClient(mongodbURI) # sets up database client

    playersGroup = app_commands.Group(name="players", description="Commands for tracking player activity.") # creates a the player commands group

    @playersGroup.command(name="toggle_heatmap_cumulation", description="Toggle the cumulation of player locations for the heatmap.")
    async def toggleHeatmapCumulation(self, interaction: discord.Interaction): # toggles the cumulation of player locations for the heatmap
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["accumulateHeatMap"]
        await collection.update_one({}, {"$set": {"accumulateHeatMap": newConfiguration}})
        await interaction.response.send_message(f"Set accumulateHeatMap to {newConfiguration}")
    
    @playersGroup.command(name="toggle_user_tracking", description="Toggle the tracking of pilots on GeoFS.")
    async def togglePlayerLocationTracking(self, interaction: discord.Interaction): # toggles saving users to the database
        db = self.mongoDBClient["OspreyEyes"]
        collection = db["configurations"]
        configuration = await collection.find_one()
        newConfiguration = not configuration["storeUsers"]
        await collection.update_one({}, {"$set": {"storeUsers": newConfiguration}})
        await interaction.response.send_message(f"Set storeUsers to {newConfiguration}")

    @playersGroup.command(name="get_online_users", description="Get the online users from the map API.")
    async def getOnlineUsers(self, interaction: discord.Interaction): # gets the online users from the map API
        stringifiedUsers = []
        currentOnlineUsers = self.mapAPI.getUsers(False)
        for user in currentOnlineUsers:
            stringifiedUsers.append(f"Callsign: {user.userInfo["callsign"]}, Account ID: {user.userInfo["id"]} Latitude: {user.coordinates[0]}, Longitude: {user.coordinates[1]} Aircraft: {user.aircraft["type"]}")
        embed = PaginatedEmbed(stringifiedUsers, title="Online Users", description="List of online users.")
        await interaction.response.send_message(embed=embed.embed, view=embed) # sends the online users in a paginated embed

    @playersGroup.command(name="generate_player_heatmap", description="Generate a heatmap of player activity locations.")
    async def heatmap(self, interaction: discord.Interaction): # generates a heatmap of player activity locations
        await interaction.response.defer()

        db = self.mongoDBClient["OspreyEyes"]
        collection = db["player_locations"]
        cursor = collection.find()
        # get the latitudes and longitudes from the database
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
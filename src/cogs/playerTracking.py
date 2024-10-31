import discord
from discord import app_commands
from discord.ext import commands, tasks
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import numpy as np
import io
from scipy.ndimage import gaussian_filter
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
from MindsEye import MindsEyeBot
from mapAPI import MapAPI

class PlayerTracker(commands.Cog):
    def __init__(self, bot):
        load_dotenv
        self.bot = bot
        self.mapAPI = MapAPI()
        DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        mongodbURI = "mongodb://adminUser:password@66.179.248.17:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource=admin"
        self.mongodbClient = AsyncIOMotorClient(mongodbURI)


    async def addPlayerLocationSnapshot(self):
        db = self.mongodbClient["OspreyEyes"]
        collection = db["player_locations"]
        online_users = self.mapAPI.getUsers(False)
        newLatitudes = np.array([user.coordinates[0] for user in online_users])
        newLongitudes = np.array([user.coordinates[1] for user in online_users])
        docs = [{"latitude": lat, "longitude": lon} for lat, lon in zip(newLatitudes, newLongitudes)]
        await collection.insert_many(docs)


    @tasks.loop(minutes=30)
    async def add_snapshot(self):
        print("Adding snapshot...")
        await self.addPlayerLocationSnapshot()
        print("Snapshot added.")

    @app_commands.command(name="toggle_heatmap_cumulation", description="Toggle the cumulation of player locations for the heatmap.")
    async def toggleHeatmapCumulation(self, interaction: discord.Interaction):
        if self.add_snapshot.is_running():
            self.add_snapshot.stop()
            await interaction.response.send_message("Heatmap cumulation stopped.")
        else:
            self.add_snapshot.start()
            await interaction.response.send_message("Heatmap cumulation started.")

    @app_commands.command(name="get_online_users", description="Get the online users from the map API.")
    async def getOnlineUsers(self, interaction: discord.Interaction):
        online_users = self.mapAPI.getUsers(False)
        for user in online_users:
            print(f"airspeed: {user.airspeed}\n userInfo: {user.userInfo}\n coordinates {user.coordinates}\n altitude: {user.altitude}\n verticalSpeed: {user.verticalSpeed}\n aircraft: {user.aircraft}")  

    @app_commands.command(name="generate_player_heatmap", description="Generate a heatmap of player activity locations.")
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
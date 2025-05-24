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
from datetime import datetime, timedelta
from collections import defaultdict
from OspreyEyes import MindsEyeBot
from paginationEmbed import PaginatedEmbed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared import mapAPI

class PlayerTracker(commands.Cog):
    def __init__(self, bot):
        # gets envs
        load_dotenv()
        self.bot = bot
        self.DATABASE_TOKEN = os.getenv('DATABASE_TOKEN')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME')
        DATABASE_IP = os.getenv('DATABASE_IP')
        DATABASE_USER = os.getenv('DATABASE_USER')
        self.mapAPI = mapAPI.MapAPI()
        self.mapAPI.disableResponseList()
        mongodbURI = f"mongodb://{DATABASE_USER}:{self.DATABASE_TOKEN}@{DATABASE_IP}:27017/?directConnection=true&serverSelectionTimeoutMS=2000&authSource={self.DATABASE_NAME}"
        self.mongoDBClient = AsyncIOMotorClient(mongodbURI) # sets up database client

    playersGroup = app_commands.Group(name="players", description="Commands for tracking player activity.") # creates a the player commands group

    @playersGroup.command(name="get_online_users", description="Get the online users from the map API.")
    async def getOnlineUsers(self, interaction: discord.Interaction): # gets the online users from the map API
        await interaction.response.defer()
        stringifiedUsers = []
        currentOnlineUsers = self.mapAPI.getUsers(False)
        for user in currentOnlineUsers:
            stringifiedUsers.append(f"Callsign: {user.userInfo["callsign"]}, Account ID: {user.userInfo["id"]} Latitude: {user.coordinates[0]}, Longitude: {user.coordinates[1]} Aircraft: {user.aircraft["type"]}")
        embed = PaginatedEmbed(stringifiedUsers, title="Online Users", description="List of online users.")
        await interaction.followup.send(embed=embed.embed, view=embed) # sends the online users in a paginated embed

    @playersGroup.command(name="generate_player_heatmap", description="Generate a heatmap of player activity locations.")
    async def heatmap(self, interaction: discord.Interaction): # generates a heatmap of player activity locations
        await interaction.response.defer()

        db = self.mongoDBClient[self.DATABASE_NAME]
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

    @playersGroup.command(name="get_aircraft_distributions", description="Get the distribution of aircraft types in relation to a specific date.")
    @app_commands.choices(time_span=[
        app_commands.Choice(name="before", value="before"),
        app_commands.Choice(name="after", value="after"),
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="all", value="all"),
    ])
    async def getAircraftDistribution(self, interaction: discord.Interaction, time_span: app_commands.Choice[str], day: int, month: int, year: int):
        await interaction.response.defer()
        # validate parameters
        if not time_span.value == "all":
            try:
                targetDate = datetime(year, month, day)
            except ValueError:
                await interaction.response.send_message("Invalid date.")
                return

        db = self.mongoDBClient[self.DATABASE_NAME]
        collection = db["aircraft"]

        # filter the documents based on the time span
        if time_span.value == "before":
            documents = collection.find({"datetime": {"$lt": targetDate}})
        elif time_span.value == "after":
            documents = collection.find({"datetime": {"$gt": targetDate}})
        elif time_span.value == "on":
            next_day = targetDate + timedelta(days=1)
            documents = collection.find({"datetime": {"$gte": targetDate, "$lt": next_day}})
        elif time_span.value == "all":
            documents = collection.find()

        aircraftTotals = defaultdict(int)
        aircraftCounts = defaultdict(int)

        # calculate the totals
        async for document in documents:
            for aircraft, count in document["aircraft"].items():
                aircraftTotals[aircraft] += count
                aircraftCounts[aircraft] += 1
        aircraftAverages = {aircraft: (aircraftTotals[aircraft] / aircraftCounts[aircraft]) for aircraft in aircraftTotals}


        # sort the totals
        sortedAverages = sorted(aircraftAverages.items(), key=lambda x: x[1], reverse=True)
        aircraftAverages = [f"**{aircraft}:** {count}" for aircraft, count in sortedAverages]
        embed = PaginatedEmbed(aircraftAverages, title="Aircraft Distributions")
        await interaction.followup.send(embed=embed.embed, view=embed)

async def setup(bot: MindsEyeBot):
    await bot.add_cog(PlayerTracker(bot))
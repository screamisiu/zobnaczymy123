import discord
from discord.ext import commands
from discord import ui

class HideUnhideView(ui.View):
    def __init__(self, channel, author, ctx):
        super().__init__(timeout=120)
        self.channel = channel
        self.author = author
        self.ctx = ctx 
        self.message = None  

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("You are not allowed to interact with this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            if item.label != "Delete":
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @ui.button(label="Unhide", style=discord.ButtonStyle.success)
    async def unhide(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.channel.set_permissions(interaction.guild.default_role, read_messages=True)
        await interaction.response.send_message(f"{self.channel.mention} has been unhidden.", ephemeral=True)

        embed = discord.Embed(
            description=f"<:icons_channel:1327829380935843941> **Channel**: {self.channel.mention}\n<:tick:1327829594954530896> **Status**: Unhidden\n <:Commands:1329004882992300083>**Reason:** Unhide request by {self.author}",
            color=0x000000
        )
        embed.add_field(name="<:U_admin:1327829252120510567> **Moderator:**", value=self.ctx.author.mention, inline=False)
        embed.set_author(name=f"Successfully Unhidden {self.channel.name}", icon_url="https://cdn.discordapp.com/attachments/1329411292532051999/1329451540028719255/Quantum_X.jpeg?ex=678a63bb&is=6789123b&hm=917647b44f40b887260074c1ccc602f0b7b8f4054c18ccc5ab6a5824bf77a9aa&")
        await self.message.edit(embed=embed, view=self)

        for item in self.children:
            if item.label != "Delete":
                item.disabled = True
        await self.message.edit(view=self)

    @ui.button(style=discord.ButtonStyle.gray, emoji="<:delete:1327842168693461022>")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class Hide(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = discord.Color.from_rgb(0, 0, 0)

    @commands.hybrid_command(
        name="hide",
        help="Hides a channel from the default role (@everyone).",
        usage="hide <channel>",
        aliases=["hidechannel"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def hide_command(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel 
        if not channel.permissions_for(ctx.guild.default_role).read_messages:
            embed = discord.Embed(
                description=f"**<:icons_channel:1327829380935843941> Channel**: {channel.mention}\n<:tick:1327829594954530896> **Status**: Already Hidden",
                color=self.color
            )
            embed.set_author(name=f"{channel.name} is Already Hidden", icon_url="https://cdn.discordapp.com/attachments/1329411292532051999/1329451540028719255/Quantum_X.jpeg?ex=678a63bb&is=6789123b&hm=917647b44f40b887260074c1ccc602f0b7b8f4054c18ccc5ab6a5824bf77a9aa&")
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)
            view = HideUnhideView(channel=channel, author=ctx.author, ctx=ctx) 
            message = await ctx.send(embed=embed, view=view)
            view.message = message
            return

        await channel.set_permissions(ctx.guild.default_role, read_messages=False)

        embed = discord.Embed(
            description=f"<:icons_channel:1327829380935843941> **Channel**: {channel.mention}\n<:tick:1327829594954530896> **Status**: Hidden\n<:Commands:1329004882992300083> **Reason:** Hide request by {ctx.author}",
            color=self.color
        )
        embed.add_field(name="<:U_admin:1327829252120510567> **Moderator:**", value=ctx.author.mention, inline=False)
        embed.set_author(name=f"Successfully Hidden {channel.name}", icon_url="https://cdn.discordapp.com/attachments/1329411292532051999/1329451540028719255/Quantum_X.jpeg?ex=678a63bb&is=6789123b&hm=917647b44f40b887260074c1ccc602f0b7b8f4054c18ccc5ab6a5824bf77a9aa&")
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)
        view = HideUnhideView(channel=channel, author=ctx.author, ctx=ctx) 
        message = await ctx.send(embed=embed, view=view)
        view.message = message


"""
@Author: Sonu Jana
    + Discord: me.sonu
    + Community: https://discord.gg/odx (Olympus Development)
    + for any queries reach out Community or DM me.
"""
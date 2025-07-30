import discord
from discord.ext import commands
from discord import ui

class LockUnlockView(ui.View):
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
            

    @ui.button(label="Lock", style=discord.ButtonStyle.danger)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(f"{self.channel.mention} has been locked.", ephemeral=True)

        embed = discord.Embed(
            description=f" **Channel**: {self.channel.mention}\n **Status**: Locked\n **Reason:** Lock request by {self.author}",
            color=0x000000
        )
        embed.add_field(name=" **Moderator:**", value=self.ctx.author.mention, inline=False)
        embed.set_author(name=f"Successfully Locked {self.channel.name}")
        await self.message.edit(embed=embed, view=self)

        for item in self.children:
            if item.label != "Delete":
                item.disabled = True
        await self.message.edit(view=self)

    @ui.button(style=discord.ButtonStyle.gray, emoji="<:delete:1327842168693461022>")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class Unlock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.color = discord.Color.from_rgb(0, 0, 0)

    @commands.hybrid_command(
        name="unlock",
        help="Unlocks a channel to allow sending messages.",
        usage="unlock <channel>",
        aliases=["unlockchannel"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unlock_command(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel 
        if channel.permissions_for(ctx.guild.default_role).send_messages is True:
            embed = discord.Embed(
                description=f"** Channel**: {channel.mention}\n**Status**: Already Unlocked",
                color=self.color
            )
            embed.set_author(name=f"{channel.name} is Already Unlocked")
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)
            view = LockUnlockView(channel=channel, author=ctx.author, ctx=ctx)  
            message = await ctx.send(embed=embed, view=view)
            view.message = message
            return

        await channel.set_permissions(ctx.guild.default_role, send_messages=True)

        embed = discord.Embed(
            description=f" **Channel**: {channel.mention}\ **Status**: Unlocked\n **Reason:** Unlock request by {ctx.author}",
            color=self.color
        )
        embed.add_field(name=" **Moderator:**", value=ctx.author.mention, inline=False)
        embed.set_author(name=f"Successfully Unlocked {channel.name}")
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)
        view = LockUnlockView(channel=channel, author=ctx.author, ctx=ctx)  
        message = await ctx.send(embed=embed, view=view)
        view.message = message


"""
@Author: Sonu Jana
    + Discord: me.sonu
    + Community: https://discord.gg/odx (Olympus Development)
    + for any queries reach out Community or DM me.
"""
import discord
from discord.ext import commands


class _antinuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """Antinuke commands"""
  
    def help_custom(self):
		      emoji = '<:security:1330393362305515560>'
		      label = "Security Commands"
		      description = "Show you Commands of Antinuke"
		      return emoji, label, description

    @commands.group()
    async def __Antinuke__(self, ctx: commands.Context):
        """`antinuke` , `antinuke enable` , `antinuke disable` , `whitelist` , `whitelist @user` , `unwhitelist` , `whitelisted` , `whitelist reset` , `extraowner` , `extraowner set` , `extraowner view` , `extraowner reset`, `nightmode` , `nightmode enable` , `nightmode disable`\n\n__**Emergency Situation**__\n`emergency` , `emergency enable` , `emergency disable` , `emergency role` , `emergency role add` , `emergency role remove` , `emergency role list` , `emergency authorise` , `emergency authorise add` , `emergency authorise remove` , `emergency authorise list`\n`emergency-situation (emgs)`"""


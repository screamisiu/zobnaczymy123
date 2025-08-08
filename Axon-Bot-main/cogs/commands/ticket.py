import discord
from discord.ext import commands
from discord.ui import View, Button, Select
import sqlite3
import os
import asyncio
from typing import Optional, Tuple

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "db/ticket.db"
        os.makedirs("db", exist_ok=True)
        self.setup_db()
        
    async def cog_load(self):
        self.bot.add_view(TicketButtonView())
        self.bot.add_view(TicketManageView(None))

    def setup_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            category_id INTEGER,
            log_channel_id INTEGER,
            staff_role_id INTEGER
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS active_tickets (
            channel_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            guild_id INTEGER
        )""")
        conn.commit()
        conn.close()

    def get_config(self, guild_id: int) -> Optional[Tuple[int, int, int]]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT category_id, log_channel_id, staff_role_id FROM guild_config WHERE guild_id = ?", (guild_id,))
        result = c.fetchone()
        conn.close()
        return result

    def add_active_ticket(self, channel_id: int, user_id: int, guild_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO active_tickets (channel_id, user_id, guild_id) VALUES (?, ?, ?)",
                 (channel_id, user_id, guild_id))
        conn.commit()
        conn.close()

    def remove_active_ticket(self, channel_id: int) -> None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM active_tickets WHERE channel_id = ?", (channel_id,))
        conn.commit()
        conn.close()

    def has_active_ticket(self, user_id: int, guild_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT channel_id FROM active_tickets WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        result = c.fetchone()
        conn.close()
        return bool(result)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def setticket(self, ctx, 
                       category: discord.CategoryChannel, 
                       log_channel: discord.TextChannel, 
                       staff_role: discord.Role):
        """Set up ticket system configuration"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO guild_config 
                (guild_id, category_id, log_channel_id, staff_role_id) 
                VALUES (?, ?, ?, ?)
            """, (ctx.guild.id, category.id, log_channel.id, staff_role.id))
            conn.commit()
            await ctx.send("✅ Ticket configuration saved for this server.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Error saving configuration: {e}", ephemeral=True)
        finally:
            conn.close()

    @commands.hybrid_command()
    async def ticketconfig(self, ctx):
        """Show current ticket configuration"""
        config = self.get_config(ctx.guild.id)
        if not config:
            return await ctx.send("❌ Ticket system is not configured.", ephemeral=True)
        
        embed = discord.Embed(title="Ticket Configuration", color=0xfcd005)
        embed.add_field(name="Category", value=f"<#{config[0]}>")
        embed.add_field(name="Log Channel", value=f"<#{config[1]}>")
        embed.add_field(name="Staff Role", value=f"<@&{config[2]}>")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def ticket(self, ctx):
        """Create a ticket panel"""
        config = self.get_config(ctx.guild.id)
        if not config:
            return await ctx.send("❌ Ticket system is not configured. Use `/setticket` first.", ephemeral=True)

        embed = discord.Embed(
            title="Tickets",
            description="Welcome to the ticket system. Click below to begin.", 
            color=0xfcd005
        )
        embed.set_image(url='https://i.imgur.com/FoI5ITb.png')
        embed.set_footer(text="Made By CodeX Development", icon_url=self.bot.user.avatar.url)
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        await ctx.send(embed=embed, view=TicketButtonView())

class TicketButtonView(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Create a Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="persistent:ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        # Fixed: Changed "TicketSetup" to "TicketSystem"
        cog = interaction.client.get_cog("TicketSystem")
        if not cog:
            return await interaction.response.send_message("❌ Ticket system is not loaded properly.", ephemeral=True)
            
        if cog.has_active_ticket(interaction.user.id, interaction.guild.id):
            return await interaction.response.send_message("You already have an active ticket!", ephemeral=True)
            
        await interaction.response.send_message("Choose a ticket reason:", view=ReasonSelectView(), ephemeral=True)

class ReasonSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        
    @discord.ui.select(
        placeholder="Select the reason...",
        options=[
            discord.SelectOption(label="Buy", value="buy", emoji="💸"),
            discord.SelectOption(label="Help", value="help", emoji="🛠️"),
            discord.SelectOption(label="report", value="report", emoji="🚫"),
        ])
    async def select_callback(self, interaction: discord.Interaction, select: Select):
        # Fixed: Changed "TicketSetup" to "TicketSystem"
        cog = interaction.client.get_cog("TicketSystem")
        if not cog:
            return await interaction.response.send_message("❌ Ticket system is not loaded properly.", ephemeral=True)
            
        config = cog.get_config(interaction.guild.id)
        if not config:
            return await interaction.response.send_message("❌ Ticket system is not configured properly.", ephemeral=True)
            
        category = interaction.guild.get_channel(config[0])
        log_channel = interaction.guild.get_channel(config[1])
        staff_role = interaction.guild.get_role(config[2])
        
        if not all([category, log_channel, staff_role]):
            return await interaction.response.send_message("❌ Ticket system configuration is invalid.", ephemeral=True)

        name_prefix = {"buy": "💸", "help": "🛠️", "report": "🚫"}[select.values[0]]
        base_name = f"{name_prefix}-{interaction.user.name}"
        channel_name = base_name
        
        counter = 1
        while discord.utils.get(category.channels, name=channel_name):
            channel_name = f"{base_name}-{counter}"
            counter += 1

        try:
            ticket_channel = await interaction.guild.create_text_channel(
                channel_name,
                category=category,
                reason=f"Ticket created by {interaction.user}"
            )
        except discord.HTTPException:
            return await interaction.response.send_message("❌ Failed to create ticket channel.", ephemeral=True)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
        }
        
        try:
            await ticket_channel.edit(overwrites=overwrites)
        except discord.HTTPException:
            await ticket_channel.delete()
            return await interaction.response.send_message("❌ Failed to set channel permissions.", ephemeral=True)

        cog.add_active_ticket(ticket_channel.id, interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

        embed = discord.Embed(
            title=f"{select.values[0].capitalize()} Ticket",
            description=f"{interaction.user.mention} opened a {select.values[0]} ticket.",
            color=0xfcd005
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        view = TicketManageView(interaction.user)
        await ticket_channel.send(interaction.user.mention, embed=embed, view=view)

        log_embed = discord.Embed(
            title="Ticket Created",
            color=0xfcd005,
            timestamp=discord.utils.utcnow()
        )
        log_embed.add_field(name="User", value=interaction.user.mention)
        log_embed.add_field(name="Reason", value=select.values[0])
        log_embed.add_field(name="Channel", value=ticket_channel.mention)
        
        try:
            await log_channel.send(embed=log_embed)
        except discord.HTTPException:
            pass

class TicketManageView(View):
    def __init__(self, ticket_owner):
        super().__init__(timeout=None)
        self.ticket_owner = ticket_owner
        
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔐", custom_id="persistent:close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        # Fixed: Changed "TicketSetup" to "TicketSystem"
        cog = interaction.client.get_cog("TicketSystem")
        if not cog:
            return await interaction.response.send_message("❌ Ticket system is not loaded properly.", ephemeral=True)
            
        config = cog.get_config(interaction.guild.id)
        staff_role = interaction.guild.get_role(config[2]) if config else None
        
        has_permission = (interaction.user == self.ticket_owner or 
                         interaction.user.guild_permissions.manage_channels or
                         (staff_role and staff_role in interaction.user.roles))
        
        if not has_permission:
            return await interaction.response.send_message("You don't have permission to close this ticket.", ephemeral=True)

        if config:
            log_channel = interaction.guild.get_channel(config[1])
            if log_channel:
                log_embed = discord.Embed(
                    title="Ticket Closed",
                    color=0xfcd005,
                    timestamp=discord.utils.utcnow()
                )
                log_embed.add_field(name="Closed by", value=interaction.user.mention)
                log_embed.add_field(name="Channel", value=f"`{interaction.channel.name}`")
                try:
                    await log_channel.send(embed=log_embed)
                except discord.HTTPException:
                    pass

        cog.remove_active_ticket(interaction.channel.id)
        await interaction.response.send_message("Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Call Staff", style=discord.ButtonStyle.blurple, emoji="🔔", custom_id="persistent:call_staff")
    async def call_staff(self, interaction: discord.Interaction, button: Button):
        # Fixed: Changed "TicketSetup" to "TicketSystem"
        cog = interaction.client.get_cog("TicketSystem")
        if not cog:
            return await interaction.response.send_message("❌ Ticket system is not loaded properly.", ephemeral=True)
            
        config = cog.get_config(interaction.guild.id)
        if not config:
            return await interaction.response.send_message("❌ Ticket system is not configured properly.", ephemeral=True)
            
        staff_role = interaction.guild.get_role(config[2])
        if not staff_role:
            return await interaction.response.send_message("❌ Staff role not found.", ephemeral=True)

        await interaction.channel.send(f"{staff_role.mention}, {interaction.user.mention} requested your help!", delete_after=15)
        await interaction.response.send_message("Staff notified!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

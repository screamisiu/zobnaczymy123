import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import json
import os

EMOJI_DOT = "<a:BlueDot:1364125472539021352>"

# Plik do przechowywania danych paneli (channel_id, message_id, options, embed, category_id) per guild
DATA_FILE = "ticket_panels.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

class EmbedEditModal(discord.ui.Modal, title="Edit Ticket Embed"):
    def __init__(self, view):
        super().__init__()
        self.view = view

        self.title_input = discord.ui.TextInput(label="Embed Title", required=False)
        self.description_input = discord.ui.TextInput(label="Description", required=False, style=discord.TextStyle.paragraph)
        self.color_input = discord.ui.TextInput(label="Color (Hex, e.g. #3498db)", required=False)
        self.image_input = discord.ui.TextInput(label="Image URL", required=False)

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.color_input)
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            color = int(self.color_input.value.replace("#", ""), 16) if self.color_input.value else 0x2B2D31
        except:
            color = 0x2B2D31

        embed = discord.Embed(
            title=self.title_input.value or "Support Ticket",
            description=self.description_input.value or "Select an option below to open a ticket.",
            color=color
        )

        if self.image_input.value:
            embed.set_image(url=self.image_input.value)

        self.view.embed = embed
        await interaction.response.edit_message(embed=embed, view=self.view)

class AddOptionModal(discord.ui.Modal, title="Add Ticket Option"):
    def __init__(self, view):
        super().__init__()
        self.view = view

        self.option_name = discord.ui.TextInput(label="Option Name", required=True)
        self.option_emoji = discord.ui.TextInput(label="Emoji (e.g. 🎟️ or <:name:id>)", required=True)
        self.staff_role = discord.ui.TextInput(label="Staff Role ID", required=True)

        self.add_item(self.option_name)
        self.add_item(self.option_emoji)
        self.add_item(self.staff_role)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            emoji = discord.PartialEmoji.from_str(self.option_emoji.value)
            if not emoji.is_unicode_emoji() and not emoji.id:
                raise ValueError("Invalid emoji format.")
        except Exception:
            await interaction.response.send_message("❌ Invalid emoji. Please use a valid Unicode emoji or custom emoji (format: <:name:id>).", ephemeral=True)
            return

        self.view.options.append({
            "label": self.option_name.value,
            "emoji": str(emoji),
            "staff_role": int(self.staff_role.value)
        })
        await interaction.response.edit_message(content="Option added.", embed=self.view.embed, view=self.view)

class TicketSetupView(discord.ui.View):
    def __init__(self, bot, author, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author
        self.guild_id = str(guild_id)
        self.embed = discord.Embed(title="Ticket Panel", description="Select an option to open a ticket.", color=0x2B2D31)
        self.options = []
        self.channel = None
        self.category_id = None  # category where tickets will be created

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.select(
        placeholder="Select an action",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Embed Edit", value="embed_edit", emoji="📝"),
            discord.SelectOption(label="Add Option", value="add_option", emoji="➕"),
            discord.SelectOption(label="Set Ticket Category", value="set_category", emoji="📂"),
            discord.SelectOption(label="Send Embed", value="send_embed", emoji="📨"),
        ]
    )
    async def menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = select.values[0]

        if value == "embed_edit":
            await interaction.response.send_modal(EmbedEditModal(self))

        elif value == "add_option":
            await interaction.response.send_modal(AddOptionModal(self))

        elif value == "set_category":
            await interaction.response.send_message("Please mention or provide the ID of the category where tickets should be created.", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and (m.channel_mentions or m.content.isdigit())

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                category = None

                # If mentioned category
                if msg.channel_mentions:
                    category = msg.channel_mentions[0]
                else:
                    # Try get category by ID from message content
                    cat_id = int(msg.content)
                    category = interaction.guild.get_channel(cat_id)

                if category is None or not isinstance(category, discord.CategoryChannel):
                    await interaction.followup.send("❌ Invalid category. Please try again with a valid category mention or ID.", ephemeral=True)
                    return

                self.category_id = category.id
                await interaction.followup.send(f"Category set to {category.name} (ID: {category.id}).", ephemeral=True)

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

        elif value == "send_embed":
            if not self.options:
                await interaction.response.send_message("❌ Please add at least one ticket option before sending the panel.", ephemeral=True)
                return
            if not self.category_id:
                await interaction.response.send_message("❌ Please set the ticket category before sending the panel.", ephemeral=True)
                return

            await interaction.response.send_message("Mention the channel to send the ticket panel.", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and m.channel_mentions

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                mentioned = msg.channel_mentions[0]

                permissions = mentioned.permissions_for(mentioned.guild.me)
                if not permissions.send_messages:
                    await interaction.followup.send("❌ I don't have permission to send messages in that channel.", ephemeral=True)
                    return

                self.channel = mentioned
                await self.send_panel(interaction)

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

    async def send_panel(self, interaction: discord.Interaction):
        # Save panel data to file for persistence
        data = load_data()
        guild_data = data.get(self.guild_id, {})

        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                for opt in self.options
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            selected_label = i.data["values"][0]

            option = next((opt for opt in self.options if opt["label"] == selected_label), None)

            if option is None:
                await i.response.send_message("Option not found.", ephemeral=True)
                return

            role = i.guild.get_role(option["staff_role"])
            overwrites = {
                i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            }
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            category = i.guild.get_channel(self.category_id)
            if category is None:
                await i.response.send_message("❌ Ticket category not found. Contact admin.", ephemeral=True)
                return

            # Use a counter from stored data or start from 1
            counter = guild_data.get("ticket_counter", 0) + 1
            guild_data["ticket_counter"] = counter
            data[self.guild_id] = guild_data
            save_data(data)

            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower().replace(' ', '-')}-{counter}",
                overwrites=overwrites,
                reason="New support ticket",
                category=category
            )

            ticket_embed = discord.Embed(
                title=f"{selected_label} Ticket",
                description=f"{i.user.mention} created a ticket. {role.mention if role else ''}",
                color=discord.Color.blurple()
            )

            view = TicketView(i.user)
            await ticket_channel.send(content=f"{i.user.mention} {role.mention if role else ''}", embed=ticket_embed, view=view)
            await i.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

        select.callback = ticket_callback

        view = discord.ui.View()
        view.add_item(select)

        sent_message = await self.channel.send(embed=self.embed, view=view)

        # Save message and channel id, options, embed, category_id in data
        guild_data["panel_message_id"] = sent_message.id
        guild_data["panel_channel_id"] = sent_message.channel.id
        guild_data["options"] = self.options
        guild_data["embed"] = {
            "title": self.embed.title,
            "description": self.embed.description,
            "color": self.embed.color.value,
            "image_url": self.embed.image.url if self.embed.image else None,
        }
        guild_data["category_id"] = self.category_id

        data[self.guild_id] = guild_data
        save_data(data)

        await interaction.followup.send("Ticket panel sent!", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self, creator):
        super().__init__(timeout=None)
        self.creator = creator
        self.claimed = False

    @discord.ui.button(label="📌 Claim", style=discord.ButtonStyle.primary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            await interaction.response.send_message("This ticket is already claimed.", ephemeral=True)
        else:
            self.claimed = True
            await interaction.channel.send(f"{interaction.user.mention} has claimed this ticket.")
            await interaction.response.defer()

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ticket will be closed. Choose below:", view=CloseOptionsView(interaction.channel, self.creator), ephemeral=True)

class CloseOptionsView(discord.ui.View):
    def __init__(self, channel, creator):
        super().__init__()
        self.channel = channel
        self.creator = creator

    @discord.ui.button(label="📄 Transcript", style=discord.ButtonStyle.secondary)
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        messages = [f"{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')} - {msg.author}: {msg.content}"
                    async for msg in self.channel.history(limit=None, oldest_first=True)]

        transcript_file = discord.File(io.BytesIO("\n".join(messages).encode()), filename=f"transcript-{self.channel.name}.txt")
        try:
            await interaction.user.send("Here is the ticket transcript:", file=transcript_file)
            await interaction.response.send_message("Transcript sent to your DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I couldn't send you a DM. Please check your privacy settings.", ephemeral=True)

    @discord.ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Deleting ticket channel...", ephemeral=True)
        await self.channel.delete(reason="Ticket closed")

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticketsetup", description="Create and send a custom ticket panel")
    async def ticketsetup(self, interaction: discord.Interaction):
        view = TicketSetupView(self.bot, interaction.user, interaction.guild.id)
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

    @app_commands.command(name="refreshpanel", description="Refresh the ticket panel by message ID")
    @app_commands.describe(message_id="ID of the ticket panel message to refresh")
    async def refreshpanel(self, interaction: discord.Interaction, message_id: str):
        guild_id = str(interaction.guild.id)
        data = load_data()
        guild_data = data.get(guild_id)
        if not guild_data:
            await interaction.response.send_message("❌ No panel data found for this server.", ephemeral=True)
            return

        panel_channel_id = guild_data.get("panel_channel_id")
        panel_message_id = guild_data.get("panel_message_id")
        options = guild_data.get("options")
        embed_data = guild_data.get("embed")
        category_id = guild_data.get("category_id")

        if str(panel_message_id) != message_id:
            await interaction.response.send_message("❌ The provided message ID does not match the saved panel message ID.", ephemeral=True)
            return

        channel = self.bot.get_channel(panel_channel_id)
        if channel is None:
            await interaction.response.send_message("❌ Cannot find the channel with the panel message.", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(panel_message_id)
        except Exception:
            await interaction.response.send_message("❌ Cannot fetch the panel message.", ephemeral=True)
            return

        embed = discord.Embed(
            title=embed_data.get("title", "Ticket Panel"),
            description=embed_data.get("description", "Select an option to open a ticket."),
            color=embed_data.get("color", 0x2B2D31)
        )
        if embed_data.get("image_url"):
            embed.set_image(url=embed_data["image_url"])

        # Rebuild the view with options loaded from file
        view = discord.ui.View()
        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                for opt in options
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            selected_label = i.data["values"][0]
            option = next((opt for opt in options if opt["label"] == selected_label), None)

            if option is None:
                await i.response.send_message("Option not found.", ephemeral=True)
                return

            role = i.guild.get_role(option["staff_role"])
            overwrites = {
                i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            }
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            category = i.guild.get_channel(category_id)
            if category is None:
                await i.response.send_message("❌ Ticket category not found. Contact admin.", ephemeral=True)
                return

            # Get and update ticket counter
            counter = guild_data.get("ticket_counter", 0) + 1
            guild_data["ticket_counter"] = counter
            data[guild_id] = guild_data
            save_data(data)

            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower().replace(' ', '-')}-{counter}",
                overwrites=overwrites,
                reason="New support ticket",
                category=category
            )

            ticket_embed = discord.Embed(
                title=f"{selected_label} Ticket",
                description=f"{i.user.mention} created a ticket. {role.mention if role else ''}",
                color=discord.Color.blurple()
            )

            view_ticket = TicketView(i.user)
            await ticket_channel.send(content=f"{i.user.mention} {role.mention if role else ''}", embed=ticket_embed, view=view_ticket)
            await i.response.send_message(f"Ticket created: {ticket_channel.mention}", ephemeral=True)

        select.callback = ticket_callback
        view.add_item(select)

        await message.edit(embed=embed, view=view)
        await interaction.response.send_message("Panel has been refreshed.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

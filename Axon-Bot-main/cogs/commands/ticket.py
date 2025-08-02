import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import json
import os

DATA_FILE = "tickets_data.json"

def load_data():
    if os.path.isfile(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

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

        # Update data in guild_data
        guild_id = self.view.guild_id
        self.view.cog.guild_data.setdefault(str(guild_id), {})
        self.view.cog.guild_data[str(guild_id)]["embed"] = {
            "title": embed.title,
            "description": embed.description,
            "color": embed.color.value,
            "image": self.image_input.value
        }
        save_data(self.view.cog.guild_data)

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

        # Add option to view.options
        self.view.options.append({
            "label": self.option_name.value,
            "emoji": str(emoji),  # save as string for serialization
            "staff_role": int(self.staff_role.value)
        })

        # Update data in guild_data
        guild_id = self.view.guild_id
        self.view.cog.guild_data.setdefault(str(guild_id), {})
        self.view.cog.guild_data[str(guild_id)]["options"] = self.view.options
        save_data(self.view.cog.guild_data)

        # Rebuild embed in case options changed (optional)
        await interaction.response.edit_message(content="Option added.", embed=self.view.embed, view=self.view)

class CategoryInputModal(discord.ui.Modal, title="Set Ticket Category ID"):
    def __init__(self, view):
        super().__init__()
        self.view = view

        self.category_id_input = discord.ui.TextInput(label="Ticket Category ID", required=True)
        self.add_item(self.category_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            category_id = int(self.category_id_input.value)
        except:
            await interaction.response.send_message("❌ Invalid category ID.", ephemeral=True)
            return

        self.view.category_id = category_id

        guild_id = self.view.guild_id
        self.view.cog.guild_data.setdefault(str(guild_id), {})
        self.view.cog.guild_data[str(guild_id)]["category_id"] = category_id
        save_data(self.view.cog.guild_data)

        await interaction.response.edit_message(content=f"Category ID set to {category_id}.", embed=self.view.embed, view=self.view)

class TicketSetupView(discord.ui.View):
    def __init__(self, bot, author, guild_id, cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author
        self.guild_id = guild_id
        self.cog = cog  # reference to cog to access guild_data
        self.embed = discord.Embed(title="Ticket Panel", description="Select an option to open a ticket.", color=0x2B2D31)
        self.options = []
        self.channel = None
        self.category_id = None

        # Load saved data if exists
        guild_data = self.cog.guild_data.get(str(self.guild_id), {})
        if "embed" in guild_data:
            e = guild_data["embed"]
            self.embed = discord.Embed(
                title=e.get("title", "Ticket Panel"),
                description=e.get("description", "Select an option below to open a ticket."),
                color=e.get("color", 0x2B2D31)
            )
            if e.get("image"):
                self.embed.set_image(url=e.get("image"))

        if "options" in guild_data:
            self.options = guild_data["options"]

        if "category_id" in guild_data:
            self.category_id = guild_data["category_id"]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.select(
        placeholder="Select an action",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Embed Edit", value="embed_edit", emoji="📝"),
            discord.SelectOption(label="Add Option", value="add_option", emoji="➕"),
            discord.SelectOption(label="Set Ticket Category", value="set_category", emoji="📁"),
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
            await interaction.response.send_modal(CategoryInputModal(self))

        elif value == "send_embed":
            if not self.category_id:
                await interaction.response.send_message("❌ Please set the ticket category first using 'Set Ticket Category'.", ephemeral=True)
                return

            await interaction.response.send_message("Mention the channel to send the ticket panel.", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                if not msg.channel_mentions:
                    await interaction.followup.send("❌ No channel mentioned in your message.", ephemeral=True)
                    return

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
        guild_id = self.guild_id
        guild_data = self.cog.guild_data.setdefault(str(guild_id), {})

        # If no options, can't send panel
        if not self.options:
            await interaction.followup.send("❌ No ticket options added yet.", ephemeral=True)
            return

        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                for opt in self.options
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            # Ticket numbering per guild:
            ticket_num = guild_data.get("ticket_counter", 0) + 1
            guild_data["ticket_counter"] = ticket_num
            save_data(self.cog.guild_data)

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

            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower()}-{ticket_num}",
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

        # Save panel message/channel id to guild_data
        guild_data["panel_message_id"] = sent_message.id
        guild_data["panel_channel_id"] = sent_message.channel.id
        save_data(self.cog.guild_data)

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
        await interaction.user.send("Here is the ticket transcript:", file=transcript_file)
        await interaction.response.send_message("Transcript sent to your DMs.", ephemeral=True)

    @discord.ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Deleting ticket channel...", ephemeral=True)
        await self.channel.delete(reason="Ticket closed")

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_data = load_data()  # key: guild_id (str), value: dict with panel, options, category_id etc.

    @app_commands.command(name="ticketsetup", description="Create and send a custom ticket panel")
    async def ticketsetup(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        view = TicketSetupView(self.bot, interaction.user, guild_id, self)
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

    @app_commands.command(name="refreshpanel", description="Refresh the ticket panel (edit the message)")
    async def refreshpanel(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_data = self.guild_data.get(str(guild_id))
        if not guild_data:
            await interaction.response.send_message("❌ No panel found to refresh. Please send the panel first.", ephemeral=True)
            return

        panel_message_id = guild_data.get("panel_message_id")
        panel_channel_id = guild_data.get("panel_channel_id")
        options = guild_data.get("options")
        embed_data = guild_data.get("embed")

        if not panel_message_id or not panel_channel_id or not embed_data or not options:
            await interaction.response.send_message("❌ No panel found to refresh. Please send the panel first.", ephemeral=True)
            return

        channel = self.bot.get_channel(panel_channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel with panel not found.", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(panel_message_id)
            embed = discord.Embed(
                title=embed_data.get("title", "Ticket Panel"),
                description=embed_data.get("description", "Select an option to open a ticket."),
                color=embed_data.get("color", 0x2B2D31)
            )
            if embed_data.get("image"):
                embed.set_image(url=embed_data.get("image"))

            # Rebuild select menu with options
            select = discord.ui.Select(
                placeholder="Select a ticket type",
                options=[
                    discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                    for opt in options
                ]
            )

            async def ticket_callback(i: discord.Interaction):
                ticket_num = guild_data.get("ticket_counter", 0) + 1
                guild_data["ticket_counter"] = ticket_num
                save_data(self.guild_data)

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

                category_id = guild_data.get("category_id")
                category = i.guild.get_channel(category_id) if category_id else None
                if category is None:
                    await i.response.send_message("❌ Ticket category not found. Contact admin.", ephemeral=True)
                    return

                ticket_channel = await i.guild.create_text_channel(
                    name=f"{selected_label.lower()}-{ticket_num}",
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

            await message.edit(embed=embed, view=view)
            await interaction.response.send_message("Panel has been refreshed.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error refreshing panel: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

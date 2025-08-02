import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import json
import os

ticket_counter = 0
DATA_FILE = "tickets.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

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
        super().__init__(timeout=None)
        self.channel = channel
        self.creator = creator

    @discord.ui.button(label="📄 Transcript", style=discord.ButtonStyle.secondary)
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        messages = [
            f"{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')} - {msg.author}: {msg.content}"
            async for msg in self.channel.history(limit=None, oldest_first=True)
        ]
        transcript_file = discord.File(io.BytesIO("\n".join(messages).encode()), filename=f"transcript-{self.channel.name}.txt")
        await interaction.user.send("Here is the ticket transcript:", file=transcript_file)
        await interaction.response.send_message("Transcript sent to your DMs.", ephemeral=True)

    @discord.ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Deleting ticket channel...", ephemeral=True)
        await self.channel.delete(reason="Ticket closed")

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
        except Exception:
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
    def __init__(self, bot, author):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.embed = discord.Embed(title="Ticket Panel", description="Select an option to open a ticket.", color=0x2B2D31)
        self.options = []
        self.channel = None
        self.category_id = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.select(
        placeholder="Select an action",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Embed Edit", value="embed_edit", emoji="📝"),
            discord.SelectOption(label="Add Option", value="add_option", emoji="➕"),
            discord.SelectOption(label="Set Category ID", value="set_category", emoji="📂"),
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
            await interaction.response.send_message("Please enter the category ID where tickets should be created:", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and m.channel == interaction.channel

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                try:
                    cat_id = int(msg.content)
                    category = interaction.guild.get_channel(cat_id)
                    if isinstance(category, discord.CategoryChannel):
                        self.category_id = cat_id
                        await interaction.followup.send(f"✅ Category set to: {category.name}", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ Provided ID is not a category.", ephemeral=True)
                except ValueError:
                    await interaction.followup.send("❌ Invalid category ID.", ephemeral=True)
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

        elif value == "send_embed":
            await interaction.response.send_message("Mention the channel to send the ticket panel.", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and m.channel == interaction.channel

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                if not msg.channel_mentions:
                    await interaction.followup.send("❌ No channel mentioned in your message.", ephemeral=True)
                    return

                self.channel = msg.channel_mentions[0]
                perms = self.channel.permissions_for(self.channel.guild.me)
                if not perms.send_messages:
                    await interaction.followup.send("❌ I don't have permission to send messages in that channel.", ephemeral=True)
                    return

                await self.send_panel(interaction)

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

    async def send_panel(self, interaction: discord.Interaction):
        global ticket_counter

        if not self.options:
            await interaction.followup.send("❌ Add at least one ticket option before sending the panel.", ephemeral=True)
            return

        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                for opt in self.options
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            global ticket_counter
            selected_label = i.data["values"][0]
            ticket_counter += 1
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

            category = None
            if self.category_id:
                category = i.guild.get_channel(self.category_id)

            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower()}-{ticket_counter}",
                overwrites=overwrites,
                category=category,
                reason="New support ticket"
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

        view = discord.ui.View(timeout=None)
        view.add_item(select)

        # Send the panel message
        message = await self.channel.send(embed=self.embed, view=view)

        # Save panel data
        data = load_data()
        data["panel"] = {
            "guild_id": interaction.guild.id,
            "channel_id": self.channel.id,
            "message_id": message.id,
            "embed": {
                "title": self.embed.title,
                "description": self.embed.description,
                "color": self.embed.color.value,
                "image": self.embed.image.url if self.embed.image else None
            },
            "options": self.options,
            "category_id": self.category_id
        }
        save_data(data)

        await interaction.followup.send(f"✅ Ticket panel sent to {self.channel.mention}!", ephemeral=True)
        self.stop()

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticketsetup", description="Setup the ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketsetup(self, interaction: discord.Interaction):
        view = TicketSetupView(self.bot, interaction.user)
        await interaction.response.send_message("Ticket Setup Panel (Only you can interact with this). Use the select below:", view=view, ephemeral=True)

    @app_commands.command(name="refreshpanel", description="Refresh the ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def refreshpanel(self, interaction: discord.Interaction):
        data = load_data()
        panel = data.get("panel")
        if not panel:
            await interaction.response.send_message("No ticket panel saved to refresh.", ephemeral=True)
            return

        guild = self.bot.get_guild(panel["guild_id"])
        if not guild:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return

        channel = guild.get_channel(panel["channel_id"])
        if not channel:
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(panel["message_id"])
        except Exception:
            await interaction.response.send_message("Panel message not found.", ephemeral=True)
            return

        embed_data = panel.get("embed", {})
        embed = discord.Embed(
            title=embed_data.get("title", "Ticket Panel"),
            description=embed_data.get("description", "Select an option below to open a ticket."),
            color=discord.Color(embed_data.get("color", 0x2B2D31))
        )
        if embed_data.get("image"):
            embed.set_image(url=embed_data["image"])

        options = panel.get("options", [])
        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                for opt in options
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            global ticket_counter
            selected_label = i.data["values"][0]
            ticket_counter += 1
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

            category = None
            cat_id = panel.get("category_id")
            if cat_id:
                category = i.guild.get_channel(cat_id)

            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower()}-{ticket_counter}",
                overwrites=overwrites,
                category=category,
                reason="New support ticket"
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
        view = discord.ui.View(timeout=None)
        view.add_item(select)

        await message.edit(embed=embed, view=view)
        await interaction.response.send_message("Ticket panel refreshed!", ephemeral=True)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    # Add persistent views after restart
    bot.add_view(TicketView(None))
    bot.add_view(CloseOptionsView(None, None))

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

bot.add_cog(TicketSystem(bot))

bot.run("YOUR_BOT_TOKEN_HERE")

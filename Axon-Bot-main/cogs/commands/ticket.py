import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import json
from datetime import datetime

TICKET_PANEL_FILE = "ticket_panel.json"
EMOJI_DOT = "<a:BlueDot:1364125472539021352>"

ticket_counter = 0

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
            await interaction.response.send_message("❌ Invalid emoji. Use Unicode or custom emoji like <:name:id>.", ephemeral=True)
            return

        self.view.options.append({
            "label": self.option_name.value,
            "emoji": str(emoji),
            "staff_role": int(self.staff_role.value)
        })
        await interaction.response.edit_message(content="Option added.", embed=self.view.embed, view=self.view)

class CategoryModal(discord.ui.Modal, title="Set Ticket Category"):
    def __init__(self, view):
        super().__init__()
        self.view = view

        self.category_id_input = discord.ui.TextInput(label="Category ID", required=False, placeholder="Leave empty for no category")
        self.add_item(self.category_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        cat_id = self.category_id_input.value.strip()
        if cat_id:
            try:
                cat_id = int(cat_id)
                self.view.category_id = cat_id
                await interaction.response.edit_message(content=f"Category set to ID: {cat_id}", embed=self.view.embed, view=self.view)
            except:
                await interaction.response.send_message("❌ Invalid Category ID.", ephemeral=True)
        else:
            self.view.category_id = None
            await interaction.response.edit_message(content="Category cleared.", embed=self.view.embed, view=self.view)

class TicketSetupView(discord.ui.View):
    def __init__(self, bot, author, embed=None, options=None, category_id=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.embed = embed or discord.Embed(title="Ticket Panel", description="Select an option to open a ticket.", color=0x2B2D31)
        self.options = options or []
        self.category_id = category_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.select(
        placeholder="Select an action",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Embed Edit", value="embed_edit", emoji="📝"),
            discord.SelectOption(label="Add Option", value="add_option", emoji="➕"),
            discord.SelectOption(label="Set Category", value="set_category", emoji="📂"),
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
            await interaction.response.send_modal(CategoryModal(self))
        elif value == "send_embed":
            # Save panel to file
            await self.save_panel()
            await interaction.response.send_message("Mention the channel to send the ticket panel.", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                if not msg.channel_mentions:
                    await interaction.followup.send("❌ No channel mentioned.", ephemeral=True)
                    return

                channel = msg.channel_mentions[0]
                perms = channel.permissions_for(channel.guild.me)
                if not perms.send_messages:
                    await interaction.followup.send("❌ I lack permission to send messages in that channel.", ephemeral=True)
                    return

                await self.send_panel(channel, interaction)

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

    async def send_panel(self, channel, interaction=None):
        global ticket_counter

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
        await channel.send(embed=self.embed, view=view)
        if interaction:
            await interaction.followup.send("Ticket panel sent!", ephemeral=True)

    async def save_panel(self):
        data = {
            "embed": {
                "title": self.embed.title,
                "description": self.embed.description,
                "color": self.embed.color.value,
                "image": self.embed.image.url if self.embed.image else None,
            },
            "options": self.options,
            "category_id": self.category_id,
        }
        with open(TICKET_PANEL_FILE, "w") as f:
            json.dump(data, f)

    @classmethod
    async def load_panel(cls, bot, author):
        try:
            with open(TICKET_PANEL_FILE, "r") as f:
                data = json.load(f)
            embed = discord.Embed(
                title=data["embed"]["title"],
                description=data["embed"]["description"],
                color=data["embed"]["color"]
            )
            if data["embed"]["image"]:
                embed.set_image(url=data["embed"]["image"])
            options = data.get("options", [])
            category_id = data.get("category_id")
            return cls(bot, author, embed=embed, options=options, category_id=category_id)
        except Exception:
            # Return default view if no saved data
            return cls(bot, author)

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
        self.view = None

    async def cog_load(self):
        # Load persistent panel on cog load
        self.view = await TicketSetupView.load_panel(self.bot, self.bot.user)
        # Add persistent view so buttons/select stay after restart
        self.bot.add_view(self.view)

    @app_commands.command(name="ticketsetup", description="Create and send a custom ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketsetup(self, interaction: discord.Interaction):
        # Start config panel for the user
        view = await TicketSetupView.load_panel(self.bot, interaction.user)
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

        # Save view ref to keep persistent buttons active
        self.view = view
        self.bot.add_view(view)

    @app_commands.command(name="refreshpanel", description="Refresh the ticket panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def refreshpanel(self, interaction: discord.Interaction):
        if not self.view or not self.view.channel:
            await interaction.response.send_message("No panel sent yet or cannot refresh.", ephemeral=True)
            return
        await self.view.send_panel(self.view.channel, interaction)
        await interaction.response.send_message("Ticket panel refreshed.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

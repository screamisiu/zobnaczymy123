import discord
from discord.ext import commands
from discord import app_commands
import asyncio

ticket_counter = 0

# ====== MODALS ======
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
        self.option_emoji = discord.ui.TextInput(label="Emoji (🎟️ or <:name:id>)", required=True)
        self.staff_role = discord.ui.TextInput(label="Staff Role ID", required=True)
        self.add_item(self.option_name)
        self.add_item(self.option_emoji)
        self.add_item(self.staff_role)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            discord.PartialEmoji.from_str(self.option_emoji.value)
        except Exception:
            await interaction.response.send_message("❌ Invalid emoji format.", ephemeral=True)
            return

        self.view.options.append({
            "label": self.option_name.value,
            "emoji": self.option_emoji.value,
            "staff_role": int(self.staff_role.value)
        })
        await interaction.response.edit_message(content="✅ Option added.", embed=self.view.embed, view=self.view)

# ====== PANEL SETUP VIEW ======
class TicketSetupView(discord.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)
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
            await interaction.response.send_message("📂 Please mention the category where tickets will be created.", ephemeral=True)
            def check(m): return m.author.id == interaction.user.id
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                if msg.channel_mentions:
                    self.category_id = msg.channel_mentions[0].id
                    await interaction.followup.send(f"✅ Category set to <#{self.category_id}>", ephemeral=True)
                else:
                    await interaction.followup.send("❌ No category mentioned.", ephemeral=True)
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

        elif value == "send_embed":
            if self.category_id is None:
                await interaction.response.send_message("❌ Set a category first.", ephemeral=True)
                return
            await interaction.response.send_message("📨 Mention the channel to send the ticket panel.", ephemeral=True)
            def check(m): return m.author.id == interaction.user.id
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30)
                if msg.channel_mentions:
                    self.channel = msg.channel_mentions[0]
                    await self.send_panel(interaction)
                else:
                    await interaction.followup.send("❌ No channel mentioned.", ephemeral=True)
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

    async def send_panel(self, interaction: discord.Interaction):
        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=opt["label"], value=opt["label"], emoji=opt["emoji"])
                for opt in self.options
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            global ticket_counter
            ticket_counter += 1
            selected_label = i.data["values"][0]
            option = next((o for o in self.options if o["label"] == selected_label), None)
            if not option:
                await i.response.send_message("❌ Option not found.", ephemeral=True)
                return
            role = i.guild.get_role(option["staff_role"])
            overwrites = {
                i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            category = i.guild.get_channel(self.category_id)
            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower()}-{ticket_counter}",
                overwrites=overwrites,
                category=category
            )
            ticket_embed = discord.Embed(
                title=f"{selected_label} Ticket",
                description=f"{i.user.mention} created a ticket. {role.mention if role else ''}",
                color=discord.Color.blurple()
            )
            view = TicketView(i.user)
            await ticket_channel.send(embed=ticket_embed, view=view)
            await i.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

        select.callback = ticket_callback
        panel_view = discord.ui.View()
        panel_view.add_item(select)

        sent_message = await self.channel.send(embed=self.embed, view=panel_view)

        # Zapisujemy w pamięci bota (RAM)
        if not hasattr(self.bot, "ticket_panels"):
            self.bot.ticket_panels = {}
        self.bot.ticket_panels[str(sent_message.id)] = {
            "guild_id": interaction.guild.id,
            "channel_id": self.channel.id,
            "category_id": self.category_id,
            "options": self.options,
            "embed": {
                "title": self.embed.title,
                "description": self.embed.description,
                "color": self.embed.color.value
            }
        }
        await interaction.followup.send("✅ Ticket panel sent and saved (in memory)!", ephemeral=True)

# ====== TICKET VIEW ======
class TicketView(discord.ui.View):
    def __init__(self, creator):
        super().__init__(timeout=None)
        self.creator = creator
        self.claimed = False

    @discord.ui.button(label="📌 Claim", style=discord.ButtonStyle.primary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.claimed:
            await interaction.response.send_message("⚠️ This ticket is already claimed.", ephemeral=True)
        else:
            self.claimed = True
            await interaction.channel.send(f"{interaction.user.mention} claimed this ticket.")
            await interaction.response.defer()

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await interaction.channel.delete(reason="Ticket closed")

# ====== COG ======
class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, "ticket_panels"):
            self.bot.ticket_panels = {}

    @app_commands.command(name="ticketsetup", description="Create and send a custom ticket panel")
    async def ticketsetup(self, interaction: discord.Interaction):
        view = TicketSetupView(self.bot, interaction.user)
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

    @app_commands.command(name="restorepanels", description="Restore ticket panels by message IDs")
    @app_commands.describe(message_ids="Space separated list of ticket panel message IDs")
    async def restorepanels(self, interaction: discord.Interaction, message_ids: str):
        ids = message_ids.split()
        restored = 0
        for message_id in ids:
            try:
                int_id = int(message_id)
            except:
                continue
            # Szukamy panelu w pamięci, jeśli już jest - pomijamy
            if hasattr(self.bot, "ticket_panels") and message_id in self.bot.ticket_panels:
                restored += 1
                continue

            # Pobieramy wiadomość
            panel_data = None
            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    try:
                        msg = await channel.fetch_message(int_id)
                        # Jeśli wiadomość ma embed i select -> uznajemy, że to panel
                        if msg and msg.components:
                            # Odtwarzamy dane panelu
                            # Niestety nie mamy oryginalnych danych, więc musimy odczytać embed
                            embed = msg.embeds[0] if msg.embeds else None
                            if embed is None:
                                continue
                            # Zakładamy brak opcji (bo nie mamy zapisu w pliku)
                            # Aby działało, trzeba pamiętać, że panel przywrócony tak ma tylko embed, ale bez opcji wyboru ticketa
                            # Można ewentualnie rozbudować parser embed albo wymagać podania dodatkowych danych
                            self.bot.ticket_panels[message_id] = {
                                "guild_id": guild.id,
                                "channel_id": channel.id,
                                "category_id": None,  # Nieznane po restarcie
                                "options": [],  # Brak opcji przywróconych automatycznie
                                "embed": {
                                    "title": embed.title or "Ticket Panel",
                                    "description": embed.description or "",
                                    "color": embed.color.value if embed.color else 0x2B2D31
                                }
                            }
                            restored += 1
                            break
                    except Exception:
                        continue

        await interaction.response.send_message(f"✅ Restored {restored} panels (in memory).", ephemeral=True)

    @app_commands.command(name="refreshpanel", description="Refresh ticket panel by message ID")
    async def refreshpanel(self, interaction: discord.Interaction, message_id: str):
        panels = self.bot.ticket_panels
        if message_id not in panels:
            await interaction.response.send_message("❌ Panel not found in memory. Use /restorepanels first.", ephemeral=True)
            return
        panel_data = panels[message_id]
        guild = self.bot.get_guild(panel_data["guild_id"])
        channel = guild.get_channel(panel_data["channel_id"])
        try:
            message = await channel.fetch_message(int(message_id))
        except:
            await interaction.response.send_message("❌ Cannot fetch message.", ephemeral=True)
            return

        select = discord.ui.Select(
            placeholder="Select a ticket type",
            options=[
                discord.SelectOption(label=o["label"], value=o["label"], emoji=o["emoji"])
                for o in panel_data["options"]
            ]
        )

        async def ticket_callback(i: discord.Interaction):
            global ticket_counter
            ticket_counter += 1
            selected_label = i.data["values"][0]
            option = next((o for o in panel_data["options"] if o["label"] == selected_label), None)
            if not option:
                await i.response.send_message("❌ Option not found.", ephemeral=True)
                return
            role = i.guild.get_role(option["staff_role"])
            overwrites = {
                i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
            category = i.guild.get_channel(panel_data["category_id"]) if panel_data["category_id"] else None
            ticket_channel = await i.guild.create_text_channel(
                name=f"{selected_label.lower()}-{ticket_counter}",
                overwrites=overwrites,
                category=category
            )
            await ticket_channel.send(f"{i.user.mention} created a ticket. {role.mention if role else ''}")
            await i.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

        select.callback = ticket_callback
        view = discord.ui.View()
        view.add_item(select)

        embed_data = panel_data["embed"]
        embed = discord.Embed(
            title=embed_data["title"],
            description=embed_data["description"],
            color=embed_data["color"]
        )
        await message.edit(embed=embed, view=view)
        await interaction.response.send_message("✅ Panel refreshed.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import json
import os

EMOJI_DOT = "<a:BlueDot:1364125472539021352>"
TICKET_CATEGORY_ID = 1336616593157001227  # Wstaw ID kategorii na tickety

ticket_counter = 0
PANEL_DATA_FILE = "ticket_panel.json"  # Plik do przechowywania ID panelu

def save_panel_data(channel_id, message_id):
    data = {
        "channel_id": channel_id,
        "message_id": message_id
    }
    with open(PANEL_DATA_FILE, "w") as f:
        json.dump(data, f)

def load_panel_data():
    if not os.path.exists(PANEL_DATA_FILE):
        return None
    with open(PANEL_DATA_FILE, "r") as f:
        return json.load(f)

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
            "emoji": emoji,
            "staff_role": int(self.staff_role.value)
        })
        await interaction.response.edit_message(content="Option added.", embed=self.view.embed, view=self.view)

class TicketSetupView(discord.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)  # Nie timeoutuj, żeby można było korzystać długo
        self.bot = bot
        self.author = author
        self.embed = discord.Embed(title="Ticket Panel", description="Select an option to open a ticket.", color=0x2B2D31)
        self.options = []
        self.channel = None
        self.message = None  # Tu będziemy trzymać wiadomość panelu

        # Załaduj istniejący panel z pliku jeśli istnieje
        panel_data = load_panel_data()
        if panel_data:
            self.channel_id = panel_data.get("channel_id")
            self.message_id = panel_data.get("message_id")
        else:
            self.channel_id = None
            self.message_id = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.select(
        placeholder="Select an action",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Embed Edit", value="embed_edit", emoji="📝"),
            discord.SelectOption(label="Add Option", value="add_option", emoji="➕"),
            discord.SelectOption(label="Send Embed", value="send_embed", emoji="📨"),
        ]
    )
    async def menu(self, interaction: discord.Interaction, select: discord.ui.Select):
        value = select.values[0]

        if value == "embed_edit":
            await interaction.response.send_modal(EmbedEditModal(self))

        elif value == "add_option":
            await interaction.response.send_modal(AddOptionModal(self))

        elif value == "send_embed":
            await interaction.response.send_message("Mention the channel to send or update the ticket panel.", ephemeral=True)

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
                await self.send_or_update_panel(interaction)

            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Timeout. Please try again.", ephemeral=True)

    async def send_or_update_panel(self, interaction: discord.Interaction):
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
                role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True) if role else discord.PermissionOverwrite()
            }

            category = i.guild.get_channel(TICKET_CATEGORY_ID)
            if category is None:
                await i.response.send_message("❌ Ticket category not found. Contact admin.", ephemeral=True)
                return

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

        # Jeśli mamy zapisane channel_id i message_id, spróbuj zaktualizować wiadomość
        if self.channel_id and self.message_id:
            try:
                channel = self.bot.get_channel(self.channel_id)
                if channel is None:
                    # Kanał nie istnieje albo bot nie ma dostępu, wyślij nową wiadomość
                    sent_message = await self.channel.send(embed=self.embed, view=view)
                    self.message = sent_message
                    save_panel_data(self.channel.id, sent_message.id)
                else:
                    msg = await channel.fetch_message(self.message_id)
                    await msg.edit(embed=self.embed, view=view)
                    self.message = msg
            except Exception as e:
                # W razie problemów (np. wiadomość usunięta), wyślij nową wiadomość
                sent_message = await self.channel.send(embed=self.embed, view=view)
                self.message = sent_message
                save_panel_data(self.channel.id, sent_message.id)
        else:
            # Jeśli brak zapisanych danych - wyślij nową wiadomość i zapisz
            sent_message = await self.channel.send(embed=self.embed, view=view)
            self.message = sent_message
            save_panel_data(self.channel.id, sent_message.id)

        await interaction.followup.send("Ticket panel sent or updated!", ephemeral=True)

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

    @app_commands.command(name="ticketsetup", description="Create and send a custom ticket panel")
    async def ticketsetup(self, interaction: discord.Interaction):
        view = TicketSetupView(self.bot, interaction.user)

        # Spróbuj załadować istniejący panel z pliku i zaktualizować go
        panel_data = load_panel_data()
        if panel_data:
            channel_id = panel_data.get("channel_id")
            message_id = panel_data.get("message_id")

            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=view.embed, view=view)
                    await interaction.response.send_message("Panel zaktualizowany!", ephemeral=True)
                    return
                except:
                    pass

        # Jeśli brak panelu lub nie udało się edytować, wyślij nową wiadomość
        await interaction.response.send_message(embed=view.embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

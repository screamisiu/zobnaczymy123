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

# Now instead of modal input for role, choose from dropdown in the View directly
# So we move role/category selection out of modal and to dropdowns in main view

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
        self.staff_role = None

        # Dropdowns for category and role will be created dynamically in interactions

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
            # Show modal only for option name and emoji, then role via dropdown
            self.add_option_modal = discord.ui.Modal(title="Add Ticket Option")
            self.option_name_input = discord.ui.TextInput(label="Option Name", required=True)
            self.option_emoji_input = discord.ui.TextInput(label="Emoji (🎟️ or <:name:id>)", required=True)
            self.add_option_modal.add_item(self.option_name_input)
            self.add_option_modal.add_item(self.option_emoji_input)

            async def modal_callback(modal_interaction: discord.Interaction):
                # Validate emoji
                try:
                    discord.PartialEmoji.from_str(self.option_emoji_input.value)
                except Exception:
                    await modal_interaction.response.send_message("❌ Invalid emoji format.", ephemeral=True)
                    return

                self.pending_option = {
                    "label": self.option_name_input.value,
                    "emoji": self.option_emoji_input.value,
                }

                # Now ask user to pick staff role from dropdown
                roles = [role for role in interaction.guild.roles if role != interaction.guild.default_role]
                role_options = [
                    discord.SelectOption(label=role.name, value=str(role.id))
                    for role in roles[:25]  # Max 25 options in select
                ]

                if not role_options:
                    await modal_interaction.response.send_message("❌ No roles available to select.", ephemeral=True)
                    return

                class RoleSelect(discord.ui.Select):
                    def __init__(self):
                        super().__init__(placeholder="Select staff role for this option", min_values=1, max_values=1, options=role_options)

                    async def callback(self, select_interaction: discord.Interaction):
                        role_id = int(select_interaction.data["values"][0])
                        self.view.pending_option["staff_role"] = role_id
                        self.view.options.append(self.view.pending_option)
                        await select_interaction.response.edit_message(content=f"✅ Added option **{self.view.pending_option['label']}** with role <@&{role_id}>.", embed=self.view.embed, view=self.view)
                        self.view.pending_option = None
                        self.view.clear_items()
                        self.view.add_item(self.view.menu)  # re-add main menu

                role_select_view = discord.ui.View()
                role_select_view.pending_option = self.pending_option
                role_select_view.menu = self.menu
                role_select_view.add_item(RoleSelect())
                await modal_interaction.response.send_message("Select the staff role for the option:", view=role_select_view, ephemeral=True)

            self.add_option_modal.on_submit = modal_callback
            await interaction.response.send_modal(self.add_option_modal)

        elif value == "set_category":
            # Show category selection dropdown
            categories = [c for c in interaction.guild.channels if isinstance(c, discord.CategoryChannel)]
            category_options = [
                discord.SelectOption(label=cat.name, value=str(cat.id))
                for cat in categories[:25]
            ]

            if not category_options:
                await interaction.response.send_message("❌ No categories found.", ephemeral=True)
                return

            class CategorySelect(discord.ui.Select):
                def __init__(self):
                    super().__init__(placeholder="Select a category for tickets", min_values=1, max_values=1, options=category_options)

                async def callback(self, select_interaction: discord.Interaction):
                    cat_id = int(select_interaction.data["values"][0])
                    self.view.category_id = cat_id
                    await select_interaction.response.edit_message(content=f"✅ Category set to <#{cat_id}>.", embed=self.view.embed, view=self.view)

            category_select_view = discord.ui.View()
            category_select_view.category_id = self.category_id
            category_select_view.embed = self.embed
            category_select_view.add_item(CategorySelect())
            await interaction.response.send_message("Select the category where tickets will be created:", view=category_select_view, ephemeral=True)

        elif value == "send_embed":
            if self.category_id is None:
                await interaction.response.send_message("❌ You need to set a category first.", ephemeral=True)
                return

            await interaction.response.send_message("Mention the channel where the ticket panel should be sent.", ephemeral=True)

            def check(m):
                return m.author.id == interaction.user.id and m.channel == interaction.channel

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

    # Other commands as you had them (restorepanels, refreshpanel)...

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))

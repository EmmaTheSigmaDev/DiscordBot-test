import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# /d:/discordbot/DiscordBot-test/bot/bot.py
# A simple Discord bot with a DM welcomer and a ticket system.
# Requirements: discord.py v2+ (pip install -U "discord.py")
# Set your bot token in the BOT_TOKEN environment variable before running.


# Load .env (for local development) and config - adjust as needed
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("DISCORD_TOKEN")  # prefer BOT_TOKEN, fall back to DISCORD_TOKEN
TICKET_CATEGORY_NAME = "Tickets"
TICKET_ROLE_NAME = "Support"      # Role that can see/claim all tickets
LOG_CHANNEL_NAME = "ticket-logs"  # Optional logs channel; create in your server or bot will create one
TICKET_CHANNEL_PREFIX = "ticket-"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# Welcomer: send a private DM to new members
@bot.event
async def on_member_join(member: discord.Member):
    try:
        dm = (
            f"Welcome to {member.guild.name}, {member.mention}!\n\n"
            "If you need help, create a ticket in the server using `!ticket create`.\n"
            "Enjoy your stay!"
        )
        await member.send(dm)
    except Exception:
        # Member may have DMs closed; ignore
        pass


# Helper: get or create the ticket category
async def get_ticket_category(guild: discord.Guild) -> discord.CategoryChannel:
    for cat in guild.categories:
        if cat.name == TICKET_CATEGORY_NAME:
            return cat
    # create category if not found (requires Manage Channels permission)
    return await guild.create_category(TICKET_CATEGORY_NAME)


# Helper: get the support role if exists
def get_support_role(guild: discord.Guild):
    for role in guild.roles:
        if role.name == TICKET_ROLE_NAME:
            return role
    return None


# Create a ticket: creates a private text channel visible to the author and support role
@bot.command(name="ticket")
async def ticket(ctx: commands.Context, action: str = None):
    if action is None:
        await ctx.send("Usage: `!ticket create` or `!ticket close` (in a ticket channel).")
        return

    action = action.lower()

    if action == "create":
        guild = ctx.guild
        if guild is None:
            await ctx.send("Tickets can only be created within a server.")
            return

        # Avoid creating multiple tickets for same user: check existing ticket channels
        existing = None
        for ch in guild.text_channels:
            if ch.name.startswith(TICKET_CHANNEL_PREFIX) and ch.topic:
                if f"owner_id={ctx.author.id}" in (ch.topic or ""):
                    existing = ch
                    break
        if existing:
            await ctx.send(f"You already have a ticket: {existing.mention}")
            return

        category = await get_ticket_category(guild)
        support_role = get_support_role(guild)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"{TICKET_CHANNEL_PREFIX}{ctx.author.display_name}-{ctx.author.discriminator}"
        # Ensure unique name if channel already exists with same name
        base_name = channel_name
        i = 1
        while discord.utils.get(guild.text_channels, name=channel_name):
            channel_name = f"{base_name}-{i}"
            i += 1

        channel = await guild.create_text_channel(
            name=channel_name[:100],
            overwrites=overwrites,
            category=category,
            topic=f"Ticket channel. owner_id={ctx.author.id}"
        )

        await channel.send(
            f"Hello {ctx.author.mention}, thank you for opening a ticket. Staff ({TICKET_ROLE_NAME}) will be with you soon.\n"
            "To close this ticket, use `!ticket close` (staff or the ticket owner)."
        )
        await ctx.send(f"Your ticket has been created: {channel.mention}")

        # optional logging
        log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            await log_channel.send(f"Ticket created: {channel.mention} by {ctx.author} ({ctx.author.id})")

    elif action == "close":
        # Close current ticket channel
        channel = ctx.channel
        if not channel.name.startswith(TICKET_CHANNEL_PREFIX):
            await ctx.send("This command can only be used inside a ticket channel.")
            return

        # Check permissions: owner or support role or manage channels
        support_role = get_support_role(ctx.guild)
        is_owner = False
        if channel.topic and f"owner_id={ctx.author.id}" in channel.topic:
            is_owner = True
        has_support = support_role in ctx.author.roles if support_role else False
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels

        if not (is_owner or has_support or can_manage):
            await ctx.send("You don't have permission to close this ticket.")
            return

        await ctx.send("This ticket will be deleted in 5 seconds. To cancel, type `cancel`.")
        try:
            def check(m):
                return m.author == ctx.author and m.channel == channel

            done, pending = await asyncio.wait(
                [bot.wait_for('message', check=check, timeout=5)],
                timeout=5
            )
            # If a message 'cancel' received, abort
            if done:
                msg = list(done)[0].result()
                if msg.content.lower().strip() == "cancel":
                    await channel.send("Ticket close canceled.")
                    return
        except asyncio.TimeoutError:
            pass

        # optional: send transcript or notify logs
        log_channel = discord.utils.get(ctx.guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            await log_channel.send(f"Ticket closed: {channel.name} by {ctx.author} ({ctx.author.id})")

        await channel.delete(reason=f"Ticket closed by {ctx.author}")

    else:
        await ctx.send("Unknown ticket action. Use `!ticket create` or `!ticket close`.")


# Small help command
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    help_text = (
        "Ticket system commands:\n"
        "`!ticket create` - create a new ticket (private channel)\n"
        "`!ticket close` - close the ticket (in a ticket channel)\n\n"
        "A welcome DM is sent automatically on server join."
    )
    await ctx.send(help_text)


if __name__ == "__main__":
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
    else:
        bot.run(TOKEN)
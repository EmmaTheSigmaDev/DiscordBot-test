import os
import asyncio
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime

# Load .env (for local development) and config - adjust as needed
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("DISCORD_TOKEN")  # prefer BOT_TOKEN, fall back to DISCORD_TOKEN

# Track bot start time for uptime command
START_TIME = time.time()
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

            # Await the single wait_for directly. asyncio.wait no longer accepts bare
            # coroutine objects in recent Python versions; awaiting is simpler here.
            msg = await bot.wait_for('message', check=check, timeout=5)
            if msg.content.lower().strip() == "cancel":
                await channel.send("Ticket close canceled.")
                return
        except asyncio.TimeoutError:
            # no cancel message within timeout; continue closing
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


def format_duration(seconds: float) -> str:
    """Format seconds into a human friendly uptime string."""
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


@bot.event
async def on_ready():
    """Called when the bot is ready. Sync slash commands."""
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    """Global handler for command errors to provide friendlier messages and avoid noisy tracebacks.

    Handles MissingRequiredArgument and MissingPermissions specially, ignores CommandNotFound,
    and logs other errors while sending a short message to the user.
    """
    # Unwrap CommandInvokeError to the original exception where applicable
    original = getattr(error, 'original', error)

    # Missing required argument (e.g. user ran `!purge` without amount)
    if isinstance(original, commands.MissingRequiredArgument):
        param_name = original.param.name if hasattr(original, 'param') else 'argument'
        cmd = ctx.command
        sig = f" {cmd.signature}" if cmd and getattr(cmd, 'signature', None) else ""
        invoked = ctx.invoked_with or (cmd.name if cmd else '')
        await ctx.send(f"Missing required argument `{param_name}`.\nUsage: `{ctx.prefix}{invoked}{sig}`")
        return

    # Missing permissions
    if isinstance(original, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
        return

    # Unknown command -> ignore silently (prevents spam when people try commands that don't exist)
    if isinstance(original, commands.CommandNotFound):
        return

    # Fallback: log and notify
    print(f"Unhandled command error in {ctx.command}: {error}")
    try:
        await ctx.send("An unexpected error occurred while running the command.")
    except Exception:
        # if sending fails, just print
        print("Also failed to send error message to channel")


@bot.tree.command(name="source-code", description="Get a link to this project's source code")
async def source_code(interaction: discord.Interaction):
    """Send a clickable link to the project's source repository."""
    repo_url = "https://github.com/EmmaTheSigmaDev/DiscordBot-test"
    await interaction.response.send_message(f"Source code: {repo_url}")


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    """Responds with bot websocket latency in ms."""
    latency = bot.latency * 1000  # seconds -> ms
    await ctx.send(f"Pong! 🏓 Latency: {latency:.0f}ms")


@bot.command(name="uptime")
async def uptime_cmd(ctx: commands.Context):
    """Shows how long the bot has been online."""
    up = time.time() - START_TIME
    await ctx.send(f"Uptime: {format_duration(up)}")


@bot.command(name="userinfo")
async def userinfo(ctx: commands.Context, member: Optional[discord.Member] = None):
    """Show information about a user (join date, roles, id)."""
    member = member or ctx.author
    embed = discord.Embed(title=f"User info — {member}", colour=discord.Colour.blue(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Top role", value=member.top_role.mention if member.top_role else "None", inline=True)
    # roles (exclude @everyone)
    roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
    embed.add_field(name="Roles", value=", ".join(roles) or "None", inline=False)
    created = member.created_at.strftime("%Y-%m-%d %H:%M UTC") if member.created_at else "Unknown"
    joined = member.joined_at.strftime("%Y-%m-%d %H:%M UTC") if member.joined_at else "Unknown"
    embed.add_field(name="Account created", value=created, inline=True)
    embed.add_field(name="Joined server", value=joined, inline=True)
    await ctx.send(embed=embed)


@bot.command(name="serverinfo")
async def serverinfo(ctx: commands.Context):
    """Show basic server stats in an embed."""
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    embed = discord.Embed(title=f"Server info — {guild.name}", colour=discord.Colour.green(), timestamp=datetime.utcnow())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else str(guild.owner), inline=True)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    text_ch = len(guild.text_channels)
    voice_ch = len(guild.voice_channels)
    embed.add_field(name="Channels", value=f"Text: {text_ch}\nVoice: {voice_ch}", inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    created = guild.created_at.strftime("%Y-%m-%d %H:%M UTC") if guild.created_at else "Unknown"
    embed.add_field(name="Created", value=created, inline=True)
    await ctx.send(embed=embed)


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
    """Kick a member from the server. Requires Kick Members permission."""
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Kicked {member}.")
        # optional logging
        log_channel = discord.utils.get(ctx.guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            await log_channel.send(f"Member kicked: {member} by {ctx.author} ({reason or 'No reason'})")
    except Exception as e:
        await ctx.send(f"Failed to kick: {e}")


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
    """Ban a member from the server. Requires Ban Members permission."""
    try:
        await member.ban(reason=reason)
        await ctx.send(f"Banned {member}.")
        log_channel = discord.utils.get(ctx.guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            await log_channel.send(f"Member banned: {member} by {ctx.author} ({reason or 'No reason'})")
    except Exception as e:
        await ctx.send(f"Failed to ban: {e}")


@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx: commands.Context, amount: int):
    """Bulk delete messages from the current channel. Usage: !purge <n>"""
    if amount <= 0:
        await ctx.send("Please provide a positive number of messages to delete.")
        return
    # limit the amount to a reasonable number
    if amount > 1000:
        await ctx.send("I can only purge up to 1000 messages at once.")
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)  # include command message
        await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)
        # optional logging
        log_channel = discord.utils.get(ctx.guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            await log_channel.send(f"Purged {len(deleted)-1} messages in {ctx.channel.mention} by {ctx.author}.")
    except Exception as e:
        await ctx.send(f"Failed to purge messages: {e}")


@bot.event
async def on_message_delete(message: discord.Message):
    """Auto-log deleted messages to the configured log channel (if present)."""
    # ignore DMs or system messages
    if not message.guild:
        return
    log_channel = discord.utils.get(message.guild.text_channels, name=LOG_CHANNEL_NAME)
    if not log_channel:
        return
    author = message.author
    embed = discord.Embed(title="Message deleted", colour=discord.Colour.red(), timestamp=datetime.utcnow())
    embed.add_field(name="Author", value=f"{author} ({author.id})", inline=True)
    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
    content = message.content or "*(no content)*"
    # truncate long content
    if len(content) > 1900:
        content = content[:1900] + "..."
    embed.add_field(name="Content", value=content, inline=False)
    if message.attachments:
        attachment_urls = "\n".join(a.url for a in message.attachments)
        embed.add_field(name="Attachments", value=attachment_urls, inline=False)
    try:
        await log_channel.send(embed=embed)
    except Exception:
        # give up silently if logging fails
        pass


if __name__ == "__main__":
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
    else:
        bot.run(TOKEN)
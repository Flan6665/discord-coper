"""A Discord server-template bot.

Flow:
  1. Invite the bot to the SOURCE server, run `/copy`. It snapshots the server's
     roles, categories, channels and permission overwrites, saves them, and
     replies with a short ID (plus the config as an attached JSON file).
  2. Invite the bot to the TARGET server, run `/paste <id>`. After a
     confirmation prompt it rebuilds that structure on the target.

Safety:
  * `/paste` requires the invoking user to have the Administrator permission.
  * `/paste` always asks for confirmation before touching anything, and the
    destructive "wipe first" behaviour is an explicit option (default: off).
  * The bot can only ever act within the permissions a server admin granted it
    when inviting it; it cannot touch roles above its own.
"""
from __future__ import annotations

import io
import json
import logging
import os

import discord
from discord import app_commands
from dotenv import load_dotenv

import serializer
import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("coper")

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready() -> None:
    await tree.sync()
    log.info("Logged in as %s (id=%s)", client.user, client.user and client.user.id)


@tree.command(name="copy", description="Snapshot this server's roles & channels and get an ID to paste elsewhere.")
async def copy(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need the **Manage Server** permission to copy this server.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    config = serializer.serialize_guild(interaction.guild)
    config_id = storage.save_config(config, owner_id=interaction.user.id)

    summary = (
        f"✅ Copied **{interaction.guild.name}**\n"
        f"• {len(config['roles'])} roles\n"
        f"• {len(config['categories'])} categories\n"
        f"• {sum(len(c['channels']) for c in config['categories']) + len(config['uncategorized_channels'])} channels\n\n"
        f"**Config ID:** `{config_id}`\n"
        f"In the target server run `/paste id:{config_id}`."
    )
    file = discord.File(
        io.BytesIO(json.dumps(config, indent=2).encode("utf-8")),
        filename=f"{config_id}.json",
    )
    await interaction.followup.send(summary, file=file, ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This confirmation isn't for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="⏳ Applying…", view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Cancelled.", view=self)
        self.stop()


@tree.command(name="paste", description="Rebuild a copied server structure here from its ID.")
@app_commands.describe(
    id="The config ID you got from /copy",
    wipe="Delete this server's existing roles & channels first (clone). Default: no, just add.",
)
async def paste(interaction: discord.Interaction, id: str, wipe: bool = False) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("Run this inside a server.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You need the **Administrator** permission to paste into this server.", ephemeral=True
        )
        return

    config = storage.load_config(id)
    if config is None:
        await interaction.response.send_message(
            f"No config found for ID `{id}`.", ephemeral=True
        )
        return

    n_channels = sum(len(c["channels"]) for c in config["categories"]) + len(
        config["uncategorized_channels"]
    )
    action = "**WIPE this server and clone**" if wipe else "add to this server"
    warn = (
        "\n\n⚠️ Wipe will delete every channel and non-protected role the bot can reach. "
        "This cannot be undone."
        if wipe
        else ""
    )
    view = ConfirmView(interaction.user.id)
    await interaction.response.send_message(
        f"About to {action} using config `{id}` "
        f"(from **{config.get('source_guild_name', 'unknown')}**): "
        f"{len(config['roles'])} roles, {n_channels} channels.{warn}\n\nConfirm?",
        view=view,
        ephemeral=True,
    )

    timed_out = await view.wait()
    if timed_out or not view.value:
        return

    reason = f"/paste by {interaction.user} (config {id})"
    result = await serializer.apply_config(interaction.guild, config, wipe=wipe, reason=reason)

    lines = [
        "✅ Done.",
        f"• Created {result.roles_created} roles, {result.categories_created} categories, "
        f"{result.channels_created} channels.",
    ]
    if wipe:
        lines.append(
            f"• Deleted {result.deleted_roles} roles and {result.deleted_channels} channels."
        )
    if result.warnings:
        shown = result.warnings[:10]
        lines.append("\n**Warnings:**\n" + "\n".join(f"• {w}" for w in shown))
        if len(result.warnings) > len(shown):
            lines.append(f"…and {len(result.warnings) - len(shown)} more.")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token."
        )
    client.run(TOKEN)


if __name__ == "__main__":
    main()

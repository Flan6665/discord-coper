"""Serialize a Discord guild's structure (roles, categories, channels and
per-channel permission overwrites) into a plain dict, and apply such a dict
back onto a target guild.

The config is intentionally structure-only: it never stores messages, members,
invites or secrets. It is the same kind of data Discord exposes through its own
"Server Template" feature, plus voice channels and a few extra channel settings.
"""
from __future__ import annotations

import discord

# Config format version. Bump when the on-disk shape changes incompatibly.
# v2: permission bitfields are stored as decimal *strings* rather than numbers,
#     so the config stays exact in JavaScript (which loses integer precision
#     above 2**53) and is interchangeable with the Node implementation.
SCHEMA_VERSION = 2


# --------------------------------------------------------------------------- #
# Export: guild -> dict
# --------------------------------------------------------------------------- #
def _overwrites_to_list(channel: discord.abc.GuildChannel) -> list[dict]:
    """Serialize a channel's permission overwrites, keyed by role name.

    Member-specific overwrites are skipped: members differ between servers, so
    they cannot be meaningfully recreated on the target.
    """
    result: list[dict] = []
    for target, overwrite in channel.overwrites.items():
        if not isinstance(target, discord.Role):
            continue
        allow, deny = overwrite.pair()
        result.append(
            {
                "role": target.name,
                "is_default": target.is_default(),  # @everyone
                "allow": str(allow.value),
                "deny": str(deny.value),
            }
        )
    return result


def _channel_common(channel: discord.abc.GuildChannel) -> dict:
    return {
        "name": channel.name,
        "position": channel.position,
        "overwrites": _overwrites_to_list(channel),
    }


def serialize_guild(guild: discord.Guild) -> dict:
    """Produce a portable, structure-only snapshot of ``guild``."""
    roles = []
    # Skip @everyone (handled separately) and managed roles (bot/integration/
    # booster roles) — those cannot be created by hand on the target.
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_default() or role.managed:
            continue
        roles.append(
            {
                "name": role.name,
                "permissions": str(role.permissions.value),
                "color": role.color.value,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "position": role.position,
            }
        )

    everyone_permissions = str(guild.default_role.permissions.value)

    categories = []
    for category in sorted(guild.categories, key=lambda c: c.position):
        cat = _channel_common(category)
        cat["channels"] = []
        for channel in sorted(category.channels, key=lambda c: c.position):
            cat["channels"].append(_serialize_leaf_channel(channel))
        categories.append(cat)

    # Channels that live outside any category.
    uncategorized = []
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        if channel.category is not None:
            continue
        uncategorized.append(_serialize_leaf_channel(channel))
    uncategorized.sort(key=lambda c: c["position"])

    return {
        "schema_version": SCHEMA_VERSION,
        "source_guild_name": guild.name,
        "everyone_permissions": everyone_permissions,
        "roles": roles,
        "categories": categories,
        "uncategorized_channels": uncategorized,
    }


def _serialize_leaf_channel(channel: discord.abc.GuildChannel) -> dict:
    data = _channel_common(channel)
    if isinstance(channel, discord.TextChannel):
        data["type"] = "text"
        data["topic"] = channel.topic
        data["nsfw"] = channel.nsfw
        data["slowmode_delay"] = channel.slowmode_delay
    elif isinstance(channel, discord.VoiceChannel):
        data["type"] = "voice"
        data["bitrate"] = channel.bitrate
        data["user_limit"] = channel.user_limit
    elif isinstance(channel, discord.StageChannel):
        data["type"] = "stage"
    elif isinstance(channel, discord.ForumChannel):
        data["type"] = "forum"
        data["topic"] = channel.topic
        data["nsfw"] = channel.nsfw
    else:
        data["type"] = "text"  # Fallback: recreate as a text channel.
    return data


# --------------------------------------------------------------------------- #
# Import: dict -> guild
# --------------------------------------------------------------------------- #
class ApplyResult:
    def __init__(self) -> None:
        self.roles_created = 0
        self.categories_created = 0
        self.channels_created = 0
        self.deleted_roles = 0
        self.deleted_channels = 0
        self.warnings: list[str] = []


def _perm(value: str | int) -> int:
    """Read a permission bitfield stored as a string (v2) or number (v1)."""
    return int(value)


def _build_overwrites(
    entries: list[dict], role_map: dict[str, discord.Role], everyone: discord.Role
) -> dict[discord.Role, discord.PermissionOverwrite]:
    overwrites: dict[discord.Role, discord.PermissionOverwrite] = {}
    for entry in entries:
        if entry.get("is_default"):
            role = everyone
        else:
            role = role_map.get(entry["role"])
        if role is None:
            continue
        allow = discord.Permissions(_perm(entry["allow"]))
        deny = discord.Permissions(_perm(entry["deny"]))
        overwrites[role] = discord.PermissionOverwrite.from_pair(allow, deny)
    return overwrites


async def apply_config(
    guild: discord.Guild,
    config: dict,
    *,
    wipe: bool,
    reason: str,
) -> ApplyResult:
    """Apply ``config`` to ``guild``.

    When ``wipe`` is True, existing non-managed roles and all channels the bot
    can delete are removed first, producing a clone. When False, the roles and
    channels are added alongside whatever already exists.
    """
    result = ApplyResult()
    me = guild.me

    if wipe:
        for channel in list(guild.channels):
            try:
                await channel.delete(reason=reason)
                result.deleted_channels += 1
            except discord.Forbidden:
                result.warnings.append(f"No permission to delete channel #{channel.name}")
            except discord.HTTPException:
                pass
        for role in list(guild.roles):
            if role.is_default() or role.managed:
                continue
            # Cannot touch roles at or above the bot's top role.
            if role >= me.top_role:
                result.warnings.append(f"Skipped role '{role.name}' (above the bot's role)")
                continue
            try:
                await role.delete(reason=reason)
                result.deleted_roles += 1
            except discord.Forbidden:
                result.warnings.append(f"No permission to delete role '{role.name}'")
            except discord.HTTPException:
                pass

    # @everyone permissions.
    try:
        await guild.default_role.edit(
            permissions=discord.Permissions(_perm(config["everyone_permissions"])),
            reason=reason,
        )
    except discord.HTTPException:
        result.warnings.append("Could not update @everyone permissions")

    # Roles, lowest position first so hierarchy ends up sane.
    role_map: dict[str, discord.Role] = {}
    for role_data in sorted(config["roles"], key=lambda r: r["position"]):
        try:
            role = await guild.create_role(
                name=role_data["name"],
                permissions=discord.Permissions(_perm(role_data["permissions"])),
                colour=discord.Colour(role_data["color"]),
                hoist=role_data["hoist"],
                mentionable=role_data["mentionable"],
                reason=reason,
            )
            role_map[role_data["name"]] = role
            result.roles_created += 1
        except discord.Forbidden:
            result.warnings.append(f"No permission to create role '{role_data['name']}'")
        except discord.HTTPException as exc:
            result.warnings.append(f"Failed to create role '{role_data['name']}': {exc}")

    everyone = guild.default_role

    # Categories and their children.
    for cat_data in sorted(config["categories"], key=lambda c: c["position"]):
        overwrites = _build_overwrites(cat_data["overwrites"], role_map, everyone)
        try:
            category = await guild.create_category(
                name=cat_data["name"], overwrites=overwrites, reason=reason
            )
            result.categories_created += 1
        except discord.HTTPException as exc:
            result.warnings.append(f"Failed to create category '{cat_data['name']}': {exc}")
            continue
        for ch_data in sorted(cat_data["channels"], key=lambda c: c["position"]):
            await _create_leaf_channel(
                guild, ch_data, category, role_map, everyone, reason, result
            )

    # Uncategorized channels.
    for ch_data in sorted(config["uncategorized_channels"], key=lambda c: c["position"]):
        await _create_leaf_channel(guild, ch_data, None, role_map, everyone, reason, result)

    return result


async def _create_leaf_channel(
    guild: discord.Guild,
    ch_data: dict,
    category: discord.CategoryChannel | None,
    role_map: dict[str, discord.Role],
    everyone: discord.Role,
    reason: str,
    result: ApplyResult,
) -> None:
    overwrites = _build_overwrites(ch_data["overwrites"], role_map, everyone)
    name = ch_data["name"]
    ch_type = ch_data.get("type", "text")
    try:
        if ch_type == "voice":
            await guild.create_voice_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                bitrate=min(ch_data.get("bitrate", 64000), guild.bitrate_limit),
                user_limit=ch_data.get("user_limit", 0),
                reason=reason,
            )
        elif ch_type == "stage":
            await guild.create_stage_channel(
                name=name, category=category, overwrites=overwrites, reason=reason
            )
        elif ch_type == "forum":
            await guild.create_forum(
                name=name,
                category=category,
                overwrites=overwrites,
                topic=ch_data.get("topic"),
                nsfw=ch_data.get("nsfw", False),
                reason=reason,
            )
        else:  # text
            await guild.create_text_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                topic=ch_data.get("topic"),
                nsfw=ch_data.get("nsfw", False),
                slowmode_delay=ch_data.get("slowmode_delay", 0),
                reason=reason,
            )
        result.channels_created += 1
    except discord.Forbidden:
        result.warnings.append(f"No permission to create channel '{name}'")
    except discord.HTTPException as exc:
        result.warnings.append(f"Failed to create channel '{name}': {exc}")

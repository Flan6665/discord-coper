/**
 * Serialize a Discord guild's structure (roles, categories, channels and
 * per-channel permission overwrites) into a plain object, and apply such an
 * object back onto a target guild.
 *
 * The config is structure-only: it never stores messages, members, invites or
 * secrets. Permission bitfields are kept as decimal strings so they survive
 * JSON round-trips exactly (JS numbers lose precision above 2**53), which also
 * makes configs interchangeable with the Python implementation.
 */
import { ChannelType, OverwriteType } from 'discord.js';

// v2: permission bitfields stored as strings. See python/serializer.py.
export const SCHEMA_VERSION = 2;

// --------------------------------------------------------------------------
// Export: guild -> object
// --------------------------------------------------------------------------

/** Serialize a channel's role-based permission overwrites, keyed by role name.
 *  Member-specific overwrites are skipped: members differ between servers. */
function overwritesToList(channel, guild) {
  const result = [];
  for (const ow of channel.permissionOverwrites.cache.values()) {
    if (ow.type !== OverwriteType.Role) continue;
    const role = guild.roles.cache.get(ow.id);
    if (!role) continue;
    result.push({
      role: role.name,
      is_default: role.id === guild.id, // @everyone
      allow: ow.allow.bitfield.toString(),
      deny: ow.deny.bitfield.toString(),
    });
  }
  return result;
}

function typeName(type) {
  switch (type) {
    case ChannelType.GuildVoice:
      return 'voice';
    case ChannelType.GuildStageVoice:
      return 'stage';
    case ChannelType.GuildForum:
      return 'forum';
    default:
      return 'text'; // text, announcement, and anything unknown
  }
}

function serializeLeafChannel(channel, guild) {
  const data = {
    name: channel.name,
    position: channel.rawPosition,
    overwrites: overwritesToList(channel, guild),
    type: typeName(channel.type),
  };
  if (data.type === 'text' || data.type === 'forum') {
    data.topic = channel.topic ?? null;
    data.nsfw = channel.nsfw ?? false;
  }
  if (data.type === 'text') {
    data.slowmode_delay = channel.rateLimitPerUser ?? 0;
  }
  if (data.type === 'voice') {
    data.bitrate = channel.bitrate ?? 64000;
    data.user_limit = channel.userLimit ?? 0;
  }
  return data;
}

/** Produce a portable, structure-only snapshot of `guild`. */
export function serializeGuild(guild) {
  // Skip @everyone (handled separately) and managed roles (bot/integration/
  // booster roles) — those cannot be created by hand on the target.
  const roles = [...guild.roles.cache.values()]
    .filter((r) => r.id !== guild.id && !r.managed)
    .sort((a, b) => a.position - b.position)
    .map((r) => ({
      name: r.name,
      permissions: r.permissions.bitfield.toString(),
      color: r.color,
      hoist: r.hoist,
      mentionable: r.mentionable,
      position: r.position,
    }));

  const allChannels = [...guild.channels.cache.values()];

  const categories = allChannels
    .filter((c) => c.type === ChannelType.GuildCategory)
    .sort((a, b) => a.rawPosition - b.rawPosition)
    .map((category) => ({
      name: category.name,
      position: category.rawPosition,
      overwrites: overwritesToList(category, guild),
      channels: allChannels
        .filter((c) => c.parentId === category.id)
        .sort((a, b) => a.rawPosition - b.rawPosition)
        .map((c) => serializeLeafChannel(c, guild)),
    }));

  const uncategorized = allChannels
    .filter((c) => c.type !== ChannelType.GuildCategory && c.parentId === null)
    .sort((a, b) => a.rawPosition - b.rawPosition)
    .map((c) => serializeLeafChannel(c, guild));

  return {
    schema_version: SCHEMA_VERSION,
    source_guild_name: guild.name,
    everyone_permissions: guild.roles.everyone.permissions.bitfield.toString(),
    roles,
    categories,
    uncategorized_channels: uncategorized,
  };
}

// --------------------------------------------------------------------------
// Import: object -> guild
// --------------------------------------------------------------------------

/** Read a permission bitfield stored as a string (v2) or number (v1). */
function perm(value) {
  return BigInt(value);
}

function buildOverwrites(entries, roleMap, guild) {
  const overwrites = [];
  for (const entry of entries) {
    const role = entry.is_default ? guild.roles.everyone : roleMap.get(entry.role);
    if (!role) continue;
    overwrites.push({ id: role.id, allow: perm(entry.allow), deny: perm(entry.deny) });
  }
  return overwrites;
}

export function countChannels(config) {
  return (
    config.categories.reduce((n, c) => n + c.channels.length, 0) +
    config.uncategorized_channels.length
  );
}

const DISCORD_TYPE = {
  text: ChannelType.GuildText,
  voice: ChannelType.GuildVoice,
  stage: ChannelType.GuildStageVoice,
  forum: ChannelType.GuildForum,
};

async function createLeafChannel(guild, data, parent, roleMap, reason, result) {
  const type = DISCORD_TYPE[data.type] ?? ChannelType.GuildText;
  const options = {
    name: data.name,
    type,
    parent: parent ? parent.id : null,
    permissionOverwrites: buildOverwrites(data.overwrites, roleMap, guild),
    reason,
  };
  if (type === ChannelType.GuildText || type === ChannelType.GuildForum) {
    if (data.topic) options.topic = data.topic;
    options.nsfw = data.nsfw ?? false;
  }
  if (type === ChannelType.GuildText) {
    options.rateLimitPerUser = data.slowmode_delay ?? 0;
  }
  if (type === ChannelType.GuildVoice) {
    options.bitrate = Math.min(data.bitrate ?? 64000, guild.maximumBitrate);
    options.userLimit = data.user_limit ?? 0;
  }
  try {
    await guild.channels.create(options);
    result.channelsCreated += 1;
  } catch (err) {
    result.warnings.push(`Failed to create channel '${data.name}': ${err.message}`);
  }
}

/**
 * Apply `config` to `guild`.
 *
 * When `wipe` is true, existing non-managed roles and all channels the bot can
 * delete are removed first, producing a clone. When false, the roles and
 * channels are added alongside whatever already exists.
 */
export async function applyConfig(guild, config, { wipe, reason }) {
  const result = {
    rolesCreated: 0,
    categoriesCreated: 0,
    channelsCreated: 0,
    deletedRoles: 0,
    deletedChannels: 0,
    warnings: [],
  };

  const me = await guild.members.fetchMe();

  if (wipe) {
    for (const channel of [...guild.channels.cache.values()]) {
      try {
        await channel.delete(reason);
        result.deletedChannels += 1;
      } catch (err) {
        result.warnings.push(`Could not delete channel #${channel.name}: ${err.message}`);
      }
    }
    for (const role of [...guild.roles.cache.values()]) {
      if (role.id === guild.id || role.managed) continue;
      // Cannot touch roles at or above the bot's top role.
      if (role.comparePositionTo(me.roles.highest) >= 0) {
        result.warnings.push(`Skipped role '${role.name}' (above the bot's role)`);
        continue;
      }
      try {
        await role.delete(reason);
        result.deletedRoles += 1;
      } catch (err) {
        result.warnings.push(`Could not delete role '${role.name}': ${err.message}`);
      }
    }
  }

  // @everyone permissions.
  try {
    await guild.roles.everyone.setPermissions(perm(config.everyone_permissions), reason);
  } catch {
    result.warnings.push('Could not update @everyone permissions');
  }

  // Roles, lowest position first so hierarchy ends up sane.
  const roleMap = new Map();
  for (const data of [...config.roles].sort((a, b) => a.position - b.position)) {
    try {
      const role = await guild.roles.create({
        name: data.name,
        permissions: perm(data.permissions),
        color: data.color,
        hoist: data.hoist,
        mentionable: data.mentionable,
        reason,
      });
      roleMap.set(data.name, role);
      result.rolesCreated += 1;
    } catch (err) {
      result.warnings.push(`Failed to create role '${data.name}': ${err.message}`);
    }
  }

  // Categories and their children.
  for (const catData of [...config.categories].sort((a, b) => a.position - b.position)) {
    let category;
    try {
      category = await guild.channels.create({
        name: catData.name,
        type: ChannelType.GuildCategory,
        permissionOverwrites: buildOverwrites(catData.overwrites, roleMap, guild),
        reason,
      });
      result.categoriesCreated += 1;
    } catch (err) {
      result.warnings.push(`Failed to create category '${catData.name}': ${err.message}`);
      continue;
    }
    for (const chData of [...catData.channels].sort((a, b) => a.position - b.position)) {
      await createLeafChannel(guild, chData, category, roleMap, reason, result);
    }
  }

  // Uncategorized channels.
  for (const chData of [...config.uncategorized_channels].sort((a, b) => a.position - b.position)) {
    await createLeafChannel(guild, chData, null, roleMap, reason, result);
  }

  return result;
}

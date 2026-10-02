/**
 * A Discord server-template bot (Node.js / discord.js implementation).
 *
 * Flow:
 *   1. Invite the bot to the SOURCE server, run `/copy`. It snapshots the
 *      server's roles, categories, channels and permission overwrites, saves
 *      them, and replies with a short ID (plus the config as a JSON file).
 *   2. Invite the bot to the TARGET server, run `/paste <id>`. After a
 *      confirmation prompt it rebuilds that structure on the target.
 *
 * Safety:
 *   * `/paste` requires the invoking user to have the Administrator permission.
 *   * `/paste` always asks for confirmation before touching anything, and the
 *     destructive "wipe first" behaviour is an explicit option (default: off).
 *   * The bot can only ever act within the permissions a server admin granted
 *     it when inviting it; it cannot touch roles above its own.
 */
import 'dotenv/config';
import {
  ActionRowBuilder,
  AttachmentBuilder,
  ButtonBuilder,
  ButtonStyle,
  Client,
  ComponentType,
  GatewayIntentBits,
  MessageFlags,
  PermissionFlagsBits,
  SlashCommandBuilder,
} from 'discord.js';

import { applyConfig, countChannels, serializeGuild } from './serializer.js';
import { loadConfig, saveConfig } from './storage.js';

const TOKEN = process.env.DISCORD_TOKEN;

const commands = [
  new SlashCommandBuilder()
    .setName('copy')
    .setDescription("Snapshot this server's roles & channels and get an ID to paste elsewhere."),
  new SlashCommandBuilder()
    .setName('paste')
    .setDescription('Rebuild a copied server structure here from its ID.')
    .addStringOption((o) =>
      o.setName('id').setDescription('The config ID you got from /copy').setRequired(true),
    )
    .addBooleanOption((o) =>
      o
        .setName('wipe')
        .setDescription("Delete this server's existing roles & channels first (clone)."),
    ),
].map((c) => c.toJSON());

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.once('clientReady', async () => {
  await client.application.commands.set(commands);
  console.log(`Logged in as ${client.user.tag} (id=${client.user.id})`);
});

async function handleCopy(interaction) {
  if (!interaction.inGuild()) {
    return interaction.reply({ content: 'Run this inside a server.', flags: MessageFlags.Ephemeral });
  }
  if (!interaction.memberPermissions.has(PermissionFlagsBits.ManageGuild)) {
    return interaction.reply({
      content: 'You need the **Manage Server** permission to copy this server.',
      flags: MessageFlags.Ephemeral,
    });
  }

  await interaction.deferReply({ flags: MessageFlags.Ephemeral });
  const config = serializeGuild(interaction.guild);
  const configId = saveConfig(config, { ownerId: interaction.user.id });

  const summary =
    `✅ Copied **${interaction.guild.name}**\n` +
    `• ${config.roles.length} roles\n` +
    `• ${config.categories.length} categories\n` +
    `• ${countChannels(config)} channels\n\n` +
    `**Config ID:** \`${configId}\`\n` +
    `In the target server run \`/paste id:${configId}\`.`;

  const file = new AttachmentBuilder(Buffer.from(JSON.stringify(config, null, 2), 'utf8'), {
    name: `${configId}.json`,
  });
  return interaction.editReply({ content: summary, files: [file] });
}

async function handlePaste(interaction) {
  if (!interaction.inGuild()) {
    return interaction.reply({ content: 'Run this inside a server.', flags: MessageFlags.Ephemeral });
  }
  if (!interaction.memberPermissions.has(PermissionFlagsBits.Administrator)) {
    return interaction.reply({
      content: 'You need the **Administrator** permission to paste into this server.',
      flags: MessageFlags.Ephemeral,
    });
  }

  const id = interaction.options.getString('id');
  const wipe = interaction.options.getBoolean('wipe') ?? false;

  const config = loadConfig(id);
  if (config === null) {
    return interaction.reply({
      content: `No config found for ID \`${id}\`.`,
      flags: MessageFlags.Ephemeral,
    });
  }

  const action = wipe ? '**WIPE this server and clone**' : 'add to this server';
  const warn = wipe
    ? '\n\n⚠️ Wipe will delete every channel and non-protected role the bot can reach. ' +
      'This cannot be undone.'
    : '';

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('confirm').setLabel('Confirm').setStyle(ButtonStyle.Danger),
    new ButtonBuilder().setCustomId('cancel').setLabel('Cancel').setStyle(ButtonStyle.Secondary),
  );

  const prompt = await interaction.reply({
    content:
      `About to ${action} using config \`${id}\` ` +
      `(from **${config.source_guild_name ?? 'unknown'}**): ` +
      `${config.roles.length} roles, ${countChannels(config)} channels.${warn}\n\nConfirm?`,
    components: [row],
    flags: MessageFlags.Ephemeral,
    withResponse: true,
  });

  let button;
  try {
    button = await prompt.resource.message.awaitMessageComponent({
      componentType: ComponentType.Button,
      filter: (i) => i.user.id === interaction.user.id,
      time: 60_000,
    });
  } catch {
    return interaction.editReply({ content: 'Timed out.', components: [] });
  }

  if (button.customId !== 'confirm') {
    return button.update({ content: 'Cancelled.', components: [] });
  }
  await button.update({ content: '⏳ Applying…', components: [] });

  const reason = `/paste by ${interaction.user.tag} (config ${id})`;
  const result = await applyConfig(interaction.guild, config, { wipe, reason });

  const lines = [
    '✅ Done.',
    `• Created ${result.rolesCreated} roles, ${result.categoriesCreated} categories, ` +
      `${result.channelsCreated} channels.`,
  ];
  if (wipe) {
    lines.push(`• Deleted ${result.deletedRoles} roles and ${result.deletedChannels} channels.`);
  }
  if (result.warnings.length > 0) {
    const shown = result.warnings.slice(0, 10);
    lines.push(`\n**Warnings:**\n${shown.map((w) => `• ${w}`).join('\n')}`);
    if (result.warnings.length > shown.length) {
      lines.push(`…and ${result.warnings.length - shown.length} more.`);
    }
  }
  return interaction.followUp({ content: lines.join('\n'), flags: MessageFlags.Ephemeral });
}

client.on('interactionCreate', async (interaction) => {
  if (!interaction.isChatInputCommand()) return;
  try {
    if (interaction.commandName === 'copy') await handleCopy(interaction);
    else if (interaction.commandName === 'paste') await handlePaste(interaction);
  } catch (err) {
    console.error(err);
  }
});

if (!TOKEN) {
  console.error('DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token.');
  process.exit(1);
}

client.login(TOKEN);

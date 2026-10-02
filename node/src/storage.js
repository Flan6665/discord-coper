/** Persist exported server configs to disk, keyed by a short random ID. */
import { randomInt } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const CONFIG_DIR = path.join(HERE, '..', 'configs');

const ID_ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789';
const ID_LENGTH = 8;

function newId() {
  let id = '';
  for (let i = 0; i < ID_LENGTH; i += 1) {
    id += ID_ALPHABET[randomInt(ID_ALPHABET.length)];
  }
  return id;
}

function pathFor(configId) {
  return path.join(CONFIG_DIR, `${configId}.json`);
}

/** Store `config` and return the generated ID used to retrieve it. */
export function saveConfig(config, { ownerId }) {
  fs.mkdirSync(CONFIG_DIR, { recursive: true });
  let configId = newId();
  while (fs.existsSync(pathFor(configId))) configId = newId();
  const payload = { ...config, _owner_id: ownerId };
  fs.writeFileSync(pathFor(configId), JSON.stringify(payload, null, 2), 'utf8');
  return configId;
}

/**
 * Load a config by ID, or return null if there is no such config.
 *
 * The ID is validated against the known alphabet/length first so a caller
 * cannot use it to read arbitrary files via path traversal.
 */
export function loadConfig(configId) {
  if (
    typeof configId !== 'string' ||
    configId.length !== ID_LENGTH ||
    [...configId].some((c) => !ID_ALPHABET.includes(c))
  ) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(pathFor(configId), 'utf8'));
  } catch {
    return null;
  }
}

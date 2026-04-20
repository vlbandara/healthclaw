#!/usr/bin/env node
/**
 * nanobot WhatsApp Bridge
 * 
 * This bridge connects WhatsApp Web to nanobot's Python backend
 * via WebSocket. It handles authentication, message forwarding,
 * and reconnection logic.
 * 
 * Usage:
 *   npm run build && npm start
 *   
 * Or with custom settings:
 *   BRIDGE_PORT=3001 AUTH_DIR=~/.nanobot/whatsapp npm start
 */

// Polyfill crypto for Baileys in ESM
import { webcrypto } from 'crypto';
if (!globalThis.crypto) {
  (globalThis as any).crypto = webcrypto;
}

import { BridgeServer } from './server.js';
import { homedir } from 'os';
import { join } from 'path';
import { existsSync, mkdirSync, readFileSync, writeFileSync, chmodSync } from 'fs';
import { randomBytes } from 'crypto';

const PORT = parseInt(process.env.BRIDGE_PORT || '3001', 10);
const HOST = (process.env.BRIDGE_HOST || '127.0.0.1').trim();
const AUTH_DIR = process.env.AUTH_DIR || join(homedir(), '.nanobot', 'whatsapp-auth');
const TOKEN_PATH = join(AUTH_DIR, 'bridge-token');

function loadOrCreateBridgeToken(): string {
  const configured = process.env.BRIDGE_TOKEN?.trim();
  if (configured) {
    return configured;
  }

  if (existsSync(TOKEN_PATH)) {
    const existing = readFileSync(TOKEN_PATH, 'utf8').trim();
    if (existing) {
      return existing;
    }
  }

  mkdirSync(AUTH_DIR, { recursive: true });
  const generated = randomBytes(32).toString('base64url');
  try {
    writeFileSync(TOKEN_PATH, generated, { encoding: 'utf8', flag: 'wx', mode: 0o600 });
    try {
      chmodSync(TOKEN_PATH, 0o600);
    } catch {
      // noop
    }
    return generated;
  } catch (error: any) {
    if (error?.code === 'EEXIST') {
      return readFileSync(TOKEN_PATH, 'utf8').trim();
    }
    throw error;
  }
}

const TOKEN = loadOrCreateBridgeToken();

if (!TOKEN) {
  console.error('Unable to resolve a WhatsApp bridge token.');
  process.exit(1);
}

console.log('🐈 nanobot WhatsApp Bridge');
console.log('========================\n');

const server = new BridgeServer(PORT, AUTH_DIR, TOKEN, HOST);

// Handle graceful shutdown
process.on('SIGINT', async () => {
  console.log('\n\nShutting down...');
  await server.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await server.stop();
  process.exit(0);
});

// Start the server
server.start().catch((error) => {
  console.error('Failed to start bridge:', error);
  process.exit(1);
});

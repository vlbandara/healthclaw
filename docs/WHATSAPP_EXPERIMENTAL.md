# WhatsApp Experimental

WhatsApp support is hidden from the public self-host beta by default. The bridge uses a Node.js WhatsApp Web adapter and should be treated as experimental.

Enable it only if you are comfortable debugging the bridge:

```env
HEALTH_ENABLE_WHATSAPP=true
HEALTH_WHATSAPP_BRIDGE_URL=ws://whatsapp-bridge:3001
WHATSAPP_BRIDGE_TOKEN=generate-a-strong-token
```

Before exposing or documenting WhatsApp in a release, run:

```bash
cd bridge
npm ci
npm run build
npm audit --audit-level=critical
```

Public launch rules:

- Do not present WhatsApp as a core feature while `HEALTH_ENABLE_WHATSAPP` is off by default.
- Do not publish screenshots containing QR codes, bridge tokens, phone numbers, or WhatsApp JIDs.
- Keep browser chat and Telegram as the supported setup paths.

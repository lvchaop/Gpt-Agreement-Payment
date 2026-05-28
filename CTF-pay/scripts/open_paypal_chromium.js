#!/usr/bin/env node
/*
 * Standalone launcher for the Google Chrome/Chromium fingerprint browser used
 * by paypal_node_rpa.js.  Browser lookup, proxy parsing, launch args, locale,
 * timezone, viewport, and init scripts are reused from paypal_node_rpa.js.
 */

const fs = require('fs');
const {
  T,
  closeBrowserSafe,
  launchProjectChromium,
} = require('./paypal_node_rpa');

function usage() {
  process.stderr.write(`Usage:
  node CTF-pay/scripts/open_paypal_chromium.js [options]

Options:
  --url URL             Page to open after launch. Defaults to about:blank.
  --proxy URL           Proxy URL passed through paypal_node_rpa.js proxy logic.
  --profile-dir DIR     Persistent profile directory.
  --payload FILE        JSON payload; supports proxy/headless/profileDir/userAgent/checkoutUrl/redirectUrl.
  --headless            Launch headless, same payload.headless=true behavior as RPA.
  --user-agent UA       Optional userAgent passed through the RPA launch options.
  -h, --help            Show this help.
`);
}

function parseArgs(argv) {
  const out = { payloadFile: '', url: '', proxy: '', profileDir: '', headless: false, userAgent: '' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') {
      usage();
      process.exit(0);
    }
    if (a === '--headless') {
      out.headless = true;
      continue;
    }
    const next = () => {
      if (i + 1 >= argv.length) throw new Error(`${a} requires a value`);
      return argv[++i];
    };
    if (a === '--url') out.url = next();
    else if (a === '--proxy') out.proxy = next();
    else if (a === '--profile-dir') out.profileDir = next();
    else if (a === '--payload') out.payloadFile = next();
    else if (a === '--user-agent') out.userAgent = next();
    else throw new Error(`unknown option: ${a}`);
  }
  return out;
}

function loadPayload(file) {
  if (!file) return {};
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

async function waitForClose(browser) {
  if (process.stdin.isTTY) {
    process.stderr.write('Google fingerprint browser is open. Press Enter to close ...\n');
    await new Promise((resolve) => {
      process.stdin.resume();
      process.stdin.once('data', resolve);
    });
    await closeBrowserSafe(browser);
    return;
  }

  process.stderr.write('stdin is not interactive; keep running until Ctrl-C or browser close.\n');
  await new Promise((resolve) => {
    process.on('SIGINT', resolve);
    process.on('SIGTERM', resolve);
  });
  await closeBrowserSafe(browser);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  try { fs.writeFileSync(T('live.log'), ''); } catch (_) {}

  const payload = loadPayload(args.payloadFile);
  if (args.proxy) payload.proxy = args.proxy;
  if (args.profileDir) payload.profileDir = args.profileDir;
  if (args.headless) payload.headless = true;
  else if (payload.headless === undefined) payload.headless = false;
  if (args.userAgent) payload.userAgent = args.userAgent;

  const startUrl = args.url || payload.checkoutUrl || payload.redirectUrl || 'about:blank';
  const launched = await launchProjectChromium(payload);
  const page = launched.browser.pages()[0] || await launched.browser.newPage();

  process.stderr.write(`[open-paypal-chromium] executable=${launched.executablePath}\n`);
  process.stderr.write(`[open-paypal-chromium] profile=${launched.profileDir}\n`);
  process.stderr.write(`[open-paypal-chromium] headless=${launched.headless}\n`);
  process.stderr.write(`[open-paypal-chromium] proxy=${launched.proxy ? launched.proxy.server : 'none'}\n`);

  if (startUrl && startUrl !== 'about:blank') {
    process.stderr.write(`[open-paypal-chromium] open=${startUrl}\n`);
    await page.goto(startUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  }

  await waitForClose(launched.browser);
}

main().catch((err) => {
  process.stderr.write(`${err && err.stack ? err.stack : err}\n`);
  process.exit(1);
});

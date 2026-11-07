// One command for the whole app on this computer: `npm run app`.
// The API records runs, the worker computes them, the site shows them. Ctrl+C stops all three.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { connect } from "node:net";
import { join } from "node:path";

const windows = process.platform === "win32";
const local = join(".venv", windows ? "Scripts" : "bin", windows ? "python.exe" : "python");
const python = existsSync(local) ? [local] : ["uv", "run", "python"];
const WATCH_SECONDS = "86400";
const WEB_PORT = 3000;

function taken(port) {
  return new Promise((done) => {
    const probe = connect(port, "127.0.0.1");
    probe.once("connect", () => {
      probe.destroy();
      done(true);
    });
    probe.once("error", () => done(false));
  });
}

const parts = [
  {
    name: "api",
    command: [
      ...python,
      "-m",
      "uvicorn",
      "multiverse_api.main:create_app",
      "--factory",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
      "--log-level",
      "warning",
    ],
  },
  {
    name: "worker",
    command: [...python, "-m", "multiverse_worker.main", "run", "--watch", WATCH_SECONDS],
  },
];

// The API trusts this port only, so a site that already runs here is used as it is.
if (await taken(WEB_PORT)) {
  console.log(`[web] already running on port ${WEB_PORT}`);
} else {
  parts.push({ name: "web", command: ["npm", "run", "dev:web"] });
}

const running = parts.map(({ name, command }) => {
  const [program, ...args] = command;
  const child = spawn(program, args, { shell: windows && program === "npm", stdio: "pipe" });
  const show = (chunk) => {
    for (const line of String(chunk).split(/\r?\n/)) {
      if (line.trim()) console.log(`[${name}] ${line}`);
    }
  };
  child.stdout.on("data", show);
  child.stderr.on("data", show);
  child.on("exit", (code) => {
    console.log(`[${name}] stopped with code ${code}`);
    stop();
  });
  return child;
});

let stopping = false;
function stop() {
  if (stopping) return;
  stopping = true;
  for (const child of running) child.kill();
  process.exitCode = 0;
}

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
console.log("MULTIVERSE: http://localhost:3000 (API on 127.0.0.1:8000). Ctrl+C stops it.");

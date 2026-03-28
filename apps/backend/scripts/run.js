const { spawnSync } = require("node:child_process");
const path = require("node:path");
const os = require("node:os");

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: node run.js <command> [args...]");
  process.exit(1);
}

const isWin = os.platform() === "win32";
const venvBinDir = path.join(
  __dirname,
  "..",
  ".venv",
  isWin ? "Scripts" : "bin",
);

let binName = args[0];
let binPath = path.join(
  venvBinDir,
  binName +
    (isWin && !binName.endsWith(".exe") && !binName.includes(".")
      ? ".exe"
      : ""),
);
let commandArgs = args.slice(1);

// Guard: ensure .venv exists before attempting to run
const fs = require("node:fs");
if (!fs.existsSync(binPath)) {
  console.error(`Error: binary not found at ${binPath}`);
  console.error(
    'Run "pnpm --filter backend run setup" first to create the virtual environment.',
  );
  process.exit(1);
}

// Celery worker on windows requires --pool=threads, prefork fails
if (
  isWin &&
  binName.includes("celery") &&
  commandArgs.includes("worker") &&
  !commandArgs.includes("--pool=threads")
) {
  commandArgs.push("--pool=threads");
}

console.log(`> Running ${binName} ${commandArgs.join(" ")}`);

const child = spawnSync(binPath, commandArgs, {
  stdio: "inherit",
  shell: false,
  cwd: path.join(__dirname, ".."),
});

process.exit(child.status ?? 1);

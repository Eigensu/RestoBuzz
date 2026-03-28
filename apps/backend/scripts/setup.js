const { spawnSync } = require("node:child_process");
const path = require("node:path");
const os = require("node:os");
const fs = require("node:fs");

const isWin = os.platform() === "win32";
const venvBinDir = path.join(
  __dirname,
  "..",
  ".venv",
  isWin ? "Scripts" : "bin",
);
const backendDir = path.join(__dirname, "..");

console.log("> Checking for existing virtual environment...");
if (!fs.existsSync(path.join(__dirname, "..", ".venv"))) {
  console.log("> Creating virtual environment...");
  const pythonCmd = isWin ? "python" : "python3";
  const venvCreate = spawnSync(pythonCmd, ["-m", "venv", ".venv"], {
    stdio: "inherit",
    shell: false,
    cwd: backendDir,
  });
  if (venvCreate.status !== 0) {
    console.error(
      "Failed to create virtual environment. Ensure python is installed and on your PATH.",
    );
    process.exit(venvCreate.status || 1);
  }
}

console.log("> Installing dependencies...");
const pipBin = path.join(venvBinDir, "pip" + (isWin ? ".exe" : ""));
const pipInstall = spawnSync(pipBin, ["install", "-r", "requirements.txt"], {
  stdio: "inherit",
  shell: false,
  cwd: backendDir,
});
if (pipInstall.status !== 0) {
  process.exit(pipInstall.status || 1);
}

console.log("> Backend setup complete.");

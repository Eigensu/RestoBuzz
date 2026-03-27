const { spawnSync } = require('child_process');
const path = require('path');
const os = require('os');

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("Usage: node run.js <command> [args...]");
  process.exit(1);
}

const isWin = os.platform() === 'win32';
const venvBinDir = path.join(__dirname, '..', '.venv', isWin ? 'Scripts' : 'bin');

let binName = args[0];
let binPath = path.join(venvBinDir, binName + (isWin && !binName.endsWith('.exe') && !binName.includes('.') ? '.exe' : ''));
let commandArgs = args.slice(1);

// Celery worker on windows requires --pool=threads, prefork fails
if (isWin && binName.includes('celery') && commandArgs.includes('worker') && !commandArgs.includes('--pool=threads')) {
  commandArgs.push('--pool=threads');
}

console.log(`> Running ${binName} ${commandArgs.join(' ')}`);

const child = spawnSync(binPath, commandArgs, {
  stdio: 'inherit',
  shell: false, 
  cwd: path.join(__dirname, '..')
});

process.exit(child.status !== null ? child.status : 1);

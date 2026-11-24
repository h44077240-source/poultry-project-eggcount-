const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('Building frontend for production...');
const frontendDir = path.join(__dirname, 'frontend');

execSync('npm install --legacy-peer-deps && npm run build', {
  cwd: frontendDir,
  stdio: 'inherit'
});

const srcDist = path.join(frontendDir, 'dist');
const destDist = path.join(__dirname, 'dist');
const backendStatic = path.join(__dirname, 'backend', 'static');

if (fs.existsSync(srcDist)) {
  fs.mkdirSync(destDist, { recursive: true });
  fs.cpSync(srcDist, destDist, { recursive: true, force: true });
  console.log('✓ Successfully mirrored build output to ./dist');

  fs.mkdirSync(backendStatic, { recursive: true });
  fs.cpSync(srcDist, backendStatic, { recursive: true, force: true });
  console.log('✓ Successfully mirrored build output to ./backend/static');
}

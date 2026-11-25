const fs = require('fs');
const path = require('path');

console.log('[BUILD] Using pre-built production frontend assets in backend/static');
const srcDist = path.join(__dirname, 'frontend', 'dist');
const destDist = path.join(__dirname, 'dist');
const backendStatic = path.join(__dirname, 'backend', 'static');

if (fs.existsSync(srcDist)) {
  fs.mkdirSync(destDist, { recursive: true });
  fs.cpSync(srcDist, destDist, { recursive: true, force: true });
  console.log('[OK] Mirrored build output to ./dist');

  fs.mkdirSync(backendStatic, { recursive: true });
  fs.cpSync(srcDist, backendStatic, { recursive: true, force: true });
  console.log('[OK] Mirrored build output to ./backend/static');
}
process.exit(0);

// Use the single user-level Playwright installation for every Node executor.
// The repository intentionally does not carry a second copy of this dependency.
const os = require('node:os');
const path = require('node:path');

const packageRoot = path.join(os.homedir(), '.local', 'share', 'playwright', 'node_modules', 'playwright');
const packageJson = require(path.join(packageRoot, 'package.json'));
if (packageJson.version !== '1.65.0') {
  throw new Error(`Expected user-level Playwright 1.65.0, found ${packageJson.version} at ${packageRoot}`);
}

module.exports = require(packageRoot);

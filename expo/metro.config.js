// Metro configuration for Expo
// We alias browser/web-only Reown AppKit modules to no-ops to avoid bundling failures in RN
// and stub a missing async-require that some packages reference.
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const projectRoot = __dirname;
const config = getDefaultConfig(projectRoot);

config.resolver = config.resolver || {};
config.resolver.alias = Object.assign({}, config.resolver.alias, {
  // Reown/AppKit browser UI – not needed for RN, stub to empty
  '@reown/appkit/core': path.resolve(projectRoot, 'src/shims/empty.ts'),
  '@reown/appkit': path.resolve(projectRoot, 'src/shims/empty.ts'),
  '@reown/appkit-scaffold-ui/basic': path.resolve(projectRoot, 'src/shims/empty.ts'),
  '@reown/appkit-scaffold-ui/w3m-modal': path.resolve(projectRoot, 'src/shims/empty.ts'),
  // Some builds try to import this internal file; provide a harmless stub
  '@expo/metro-config/build/async-require.js': path.resolve(projectRoot, 'src/shims/async-require.ts'),
});

module.exports = config;

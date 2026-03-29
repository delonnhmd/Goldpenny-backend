module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      // Optional alias – safe to keep
      ['module-resolver', { alias: { '@': './src' } }],
      // Strip console.* in production builds (optional)
      ['transform-remove-console', { exclude: ['error', 'warn'] }],
      // ⚠️ MUST be last: required by react-native-reanimated
      'react-native-reanimated/plugin',
    ],
  };
};

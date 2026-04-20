/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import { Platform } from 'react-native';
import { uiTokens } from '@/theme/tokens';

const tintColorLight = uiTokens.action;
const tintColorDark = uiTokens.action;

export const Colors = {
  light: {
    text: uiTokens.text.onLight,
    background: uiTokens.bg.sheet,
    tint: tintColorLight,
    icon: uiTokens.text.onLightMuted,
    tabIconDefault: uiTokens.text.onLightMuted,
    tabIconSelected: tintColorLight,
  },
  dark: {
    text: uiTokens.text.onDark,
    background: uiTokens.bg.app,
    tint: tintColorDark,
    icon: uiTokens.text.onDarkMuted,
    tabIconDefault: uiTokens.text.onDarkMuted,
    tabIconSelected: tintColorDark,
  },
};

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    serif: "Georgia, 'Times New Roman', serif",
    rounded: "'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Meiryo, 'MS PGothic', sans-serif",
    mono: "SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  },
});

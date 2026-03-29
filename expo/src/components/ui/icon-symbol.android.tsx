import { View, StyleProp, ViewStyle } from 'react-native';

export function IconSymbol({
  size = 24,
  color,
  style,
  weight,
}: {
  name?: string;
  size?: number;
  color?: string;
  style?: StyleProp<ViewStyle>;
  // support optional weight prop used by some callers
  weight?: string;
}) {
  return <View style={[{ width: size, height: size, backgroundColor: 'transparent' }, style]} />;
}
export default IconSymbol;

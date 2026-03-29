import React from 'react';
import { DimensionValue, StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';
import { useResponsiveValue } from '@/hooks/useResponsiveValue';

export default function ResponsiveGrid({
  children,
  minItemWidth = 300,
  gap = theme.spacing.md,
}: {
  children: React.ReactNode;
  minItemWidth?: number;
  gap?: number;
}) {
  const columns = useResponsiveValue<number>(
    {
      mobile: 1,
      largeMobile: 1,
      tablet: 2,
      desktop: 2,
    },
    1,
  );

  const widthPercent: DimensionValue = `${100 / columns}%`;

  return (
    <View style={[styles.grid, { gap }]}> 
      {React.Children.map(children, (child, index) => (
        <View
          key={`grid_${index}`}
          style={[
            styles.cell,
            {
              width: columns === 1 ? '100%' : widthPercent,
              minWidth: columns === 1 ? undefined : minItemWidth,
              paddingHorizontal: columns === 1 ? 0 : gap / 2,
            },
          ]}
        >
          {child}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -theme.spacing.sm,
  },
  cell: {
    marginBottom: 0,
  },
});

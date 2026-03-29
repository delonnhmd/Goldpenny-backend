import React from 'react';

import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import { theme } from '@/design/theme';

export default function GameplayHomeTemplate({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <PageContainer>
      <ContentStack gap={theme.spacing.md}>{children}</ContentStack>
    </PageContainer>
  );
}

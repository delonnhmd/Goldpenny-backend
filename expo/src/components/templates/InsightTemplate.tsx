import React from 'react';

import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import ResponsiveGrid from '@/components/layout/ResponsiveGrid';

export default function InsightTemplate({
  primary,
  secondary,
}: {
  primary: React.ReactNode;
  secondary?: React.ReactNode;
}) {
  if (!secondary) {
    return (
      <PageContainer>
        <ContentStack>{primary}</ContentStack>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <ResponsiveGrid>
        <ContentStack>{primary}</ContentStack>
        <ContentStack>{secondary}</ContentStack>
      </ResponsiveGrid>
    </PageContainer>
  );
}

import React from 'react';

import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';

export default function OnboardingTemplate({
  hero,
  guide,
  unlocks,
}: {
  hero: React.ReactNode;
  guide?: React.ReactNode;
  unlocks?: React.ReactNode;
}) {
  return (
    <PageContainer>
      <ContentStack>
        {hero}
        {guide}
        {unlocks}
      </ContentStack>
    </PageContainer>
  );
}

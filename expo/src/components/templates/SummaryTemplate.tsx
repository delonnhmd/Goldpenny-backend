import React from 'react';

import PageContainer from '@/components/layout/PageContainer';

export default function SummaryTemplate({
  children,
}: {
  children: React.ReactNode;
}) {
  return <PageContainer>{children}</PageContainer>;
}

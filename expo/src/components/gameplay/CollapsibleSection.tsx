import React from 'react';

import ExpandCollapseView from '@/components/motion/ExpandCollapseView';

export default function CollapsibleSection({
  expanded,
  children,
}: {
  expanded: boolean;
  children: React.ReactNode;
}) {

  return (
    <ExpandCollapseView expanded={expanded}>
      <React.Fragment>{children}</React.Fragment>
    </ExpandCollapseView>
  );
}

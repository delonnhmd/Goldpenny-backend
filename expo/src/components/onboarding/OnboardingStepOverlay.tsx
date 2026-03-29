import React, { useEffect, useState } from 'react';

import { useOnboarding } from '@/features/onboarding';
import { recordInfo } from '@/lib/logger';

import OnboardingTooltip from './OnboardingTooltip';

export default function OnboardingStepOverlay() {
  const onboarding = useOnboarding();
  const [busyAction, setBusyAction] = useState<'continue' | 'skip' | null>(null);

  useEffect(() => {
    if (!onboarding.isActive || !onboarding.currentStep) return;
    if (
      !__DEV__
      && process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS !== 'true'
      && process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS !== '1'
    ) {
      return;
    }
    recordInfo('onboarding', 'Onboarding overlay mounted.', {
      action: 'overlay_mount',
      context: {
        stepKey: onboarding.currentStep.key,
        route: onboarding.currentStep.route,
      },
    });

    return () => {
      recordInfo('onboarding', 'Onboarding overlay unmounted.', {
        action: 'overlay_unmount',
        context: {
          stepKey: onboarding.currentStep?.key || null,
          route: onboarding.currentStep?.route || null,
        },
      });
    };
  }, [onboarding.currentStep, onboarding.isActive]);

  if (!onboarding.isActive || !onboarding.currentStep) return null;

  const handleContinue = async () => {
    if (!onboarding.canContinueCurrentStep) return;
    setBusyAction('continue');
    try {
      await onboarding.continueCurrentStep();
    } finally {
      setBusyAction(null);
    }
  };

  const handleSkip = async () => {
    setBusyAction('skip');
    try {
      await onboarding.skipOnboarding();
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <OnboardingTooltip
      progressLabel={onboarding.progressLabel}
      title={onboarding.currentStep.title}
      message={onboarding.currentStep.body}
      statusMessage={onboarding.requirementStatus}
      blockedMessage={onboarding.blockedNavigationMessage}
      continueLabel={onboarding.continueLabel}
      onContinue={onboarding.canContinueCurrentStep ? handleContinue : undefined}
      onSkip={handleSkip}
      continueDisabled={!onboarding.canContinueCurrentStep}
      continueLoading={busyAction === 'continue'}
      skipLoading={busyAction === 'skip'}
    />
  );
}

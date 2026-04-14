import React from 'react';
import { Redirect, router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import SectionCard from '@/components/ui/SectionCard';
import { theme } from '@/design/theme';
import { useAuth } from '@/features/auth';

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Not available';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Not available';
  return parsed.toLocaleString();
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

export default function AccountProfileScreen() {
  const auth = useAuth();

  if (auth.status === 'loading') {
    return (
      <AppShell title="Account" subtitle="Restoring account details">
        <PageContainer>
          <ContentStack style={styles.content}>
            <SectionCard title="Loading account" summary="Checking the linked player profile for this session.">
              <Text style={styles.note}>One moment while your account summary loads.</Text>
            </SectionCard>
          </ContentStack>
        </PageContainer>
      </AppShell>
    );
  }

  if (!auth.isAuthenticated || !auth.session) {
    return <Redirect href="/auth/login" />;
  }

  const { account, player_profile: playerProfile } = auth.session;

  const handleLogout = async () => {
    await auth.signOut();
    router.replace('/auth/login');
  };

  return (
    <AppShell title="Account" subtitle="Profile, session, and linked player">
      <PageContainer>
        <ContentStack style={styles.content}>
          <SectionCard
            title="Account Details"
            summary="Authentication identity is stored separately from gameplay state, with one linked player profile per account."
          >
            <InfoRow label="Email" value={account.email} />
            <InfoRow label="Status" value={account.status} />
            <InfoRow label="Auth Provider" value={account.auth_provider} />
            <InfoRow label="Created" value={formatTimestamp(account.created_at)} />
            <InfoRow label="Last Login" value={formatTimestamp(account.last_login_at)} />
          </SectionCard>

          <SectionCard
            title="Linked Player Profile"
            summary="This is the gameplay profile that loads after sign-in and session restore."
          >
            <InfoRow label="Player ID" value={playerProfile.id} />
            <InfoRow label="Display Name" value={playerProfile.display_name || 'Not set yet'} />
            <InfoRow label="Current Job" value={playerProfile.current_job || 'Unassigned'} />
            <InfoRow label="Region" value={playerProfile.region || 'Unknown'} />
            <InfoRow label="Cash" value={`${playerProfile.cash_xgp.toFixed(2)} XGP`} />
            <InfoRow label="Debt" value={`${playerProfile.debt_xgp.toFixed(2)} XGP`} />
            <InfoRow label="Health / Stress" value={`${playerProfile.health} / ${playerProfile.stress}`} />
            <InfoRow label="Profile Created" value={formatTimestamp(playerProfile.created_at)} />
          </SectionCard>

          <SecondaryButton
            label="Back To Game"
            onPress={() => router.replace('/gameplay')}
            style={styles.fullWidthButton}
          />
          <PrimaryButton
            label="Log Out"
            onPress={handleLogout}
            style={styles.fullWidthButton}
          />
        </ContentStack>
      </PageContainer>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingTop: theme.spacing.xl,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  infoLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  infoValue: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
    fontWeight: '700',
    flexShrink: 1,
    textAlign: 'right',
  },
  note: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  fullWidthButton: {
    width: '100%',
  },
});

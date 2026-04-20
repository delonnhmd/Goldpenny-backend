import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { alpha, theme } from '@/design/theme';
import { formatMoney } from '@/lib/gameplayFormatters';
import type { ActiveBusinessProfile, BusinessMarketListing } from '@/types/business';

interface BusinessMarketPanelProps {
  listings: BusinessMarketListing[];
  selectedListingId: string | null;
  comparedListingIds: string[];
  activeBusinessProfile: ActiveBusinessProfile | null;
  canTransact: boolean;
  onInspectListing: (listingId: string) => void;
  onToggleCompare: (listingId: string) => void;
  onBuyListing: (listing: BusinessMarketListing) => void;
  onAdvancePhase: () => void;
}

function scoreTone(score: number): string {
  if (score >= 78) return theme.gameUi.success;
  if (score >= 58) return theme.gameUi.warning;
  return theme.gameUi.danger;
}

export default function BusinessMarketPanel({
  listings,
  selectedListingId,
  comparedListingIds,
  activeBusinessProfile,
  canTransact,
  onInspectListing,
  onToggleCompare,
  onBuyListing,
  onAdvancePhase,
}: BusinessMarketPanelProps) {
  const comparedListings = useMemo(
    () => listings.filter((listing) => comparedListingIds.includes(listing.listing_id)).slice(0, 2),
    [comparedListingIds, listings],
  );

  return (
    <View style={styles.section}>
      {activeBusinessProfile ? (
        <View style={styles.activeCard}>
          <Text style={styles.sectionTitle}>Active Business Growth</Text>
          <Text style={styles.activeTitle}>{activeBusinessProfile.display_name}</Text>
          <Text style={styles.activeSubtitle}>
            {activeBusinessProfile.growth_phase_label} · {activeBusinessProfile.location_label}
          </Text>

          <View style={styles.metricsRow}>
            <View style={styles.metricCard}>
              <Text style={styles.metricLabel}>Employees</Text>
              <Text style={styles.metricValue}>
                {activeBusinessProfile.employees}/{activeBusinessProfile.employee_capacity}
              </Text>
              <Text style={styles.metricMeta}>
                NPC {activeBusinessProfile.npc_employees} · Players {activeBusinessProfile.player_employees}
              </Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricLabel}>Wages</Text>
              <Text style={styles.metricValue}>{formatMoney(activeBusinessProfile.wage_cost_xgp)}</Text>
              <Text style={styles.metricMeta}>Open slots {activeBusinessProfile.open_slots}</Text>
            </View>
            <View style={styles.metricCard}>
              <Text style={styles.metricLabel}>Performance</Text>
              <Text style={[styles.metricValue, { color: scoreTone(activeBusinessProfile.performance_score) }]}>
                {activeBusinessProfile.performance_score}/100
              </Text>
              <Text style={styles.metricMeta}>Demand {activeBusinessProfile.demand_score}/100</Text>
            </View>
          </View>

          <Text style={styles.toolTitle}>Management tools</Text>
          <Text style={styles.toolBody}>{activeBusinessProfile.management_tools.join(' · ')}</Text>
          <Text style={styles.phaseHint}>{activeBusinessProfile.phase_progress_label}</Text>

          <PrimaryButton
            label={activeBusinessProfile.next_phase_label ? `Advance To ${activeBusinessProfile.next_phase_label}` : 'Top Phase Reached'}
            onPress={activeBusinessProfile.next_phase_label ? onAdvancePhase : undefined}
            disabled={!activeBusinessProfile.next_phase_label}
          />
        </View>
      ) : null}

      <Text style={styles.sectionTitle}>Businesses For Sale</Text>
      <Text style={styles.sectionBody}>
        Inspect, compare, and buy businesses from the city market instead of generic screen buttons.
      </Text>

      {listings.map((listing) => {
        const isSelected = selectedListingId === listing.listing_id;
        const compared = comparedListingIds.includes(listing.listing_id);
        const buyDisabled = !canTransact || !listing.buyable || listing.locked;

        return (
          <View
            key={listing.listing_id}
            style={[
              styles.listingCard,
              isSelected ? styles.listingCardSelected : null,
              compared ? styles.listingCardCompared : null,
            ]}
          >
            <View style={styles.listingHeader}>
              <View style={styles.listingTitleWrap}>
                <Text style={styles.listingTitle}>{listing.listing_name}</Text>
                <Text style={styles.listingMeta}>
                  {listing.growth_phase_label} · {listing.location_label}
                </Text>
              </View>
              <Text style={styles.listingPrice}>{formatMoney(listing.price_xgp)}</Text>
            </View>

            <View style={styles.metricPills}>
              <Text style={styles.metricPill}>Demand {listing.demand_score}</Text>
              <Text style={styles.metricPill}>Rep {listing.reputation_score}</Text>
              <Text style={styles.metricPill}>Traffic {listing.traffic_potential}</Text>
              <Text style={styles.metricPill}>Perf {listing.performance_score}</Text>
            </View>

            <Text style={styles.listingDetail}>
              Employees {listing.employees}/{listing.employee_capacity} · Wage cost {formatMoney(listing.wage_cost_xgp)}
            </Text>
            <Text style={styles.listingDetail}>{listing.compare_note}</Text>
            <Text style={styles.listingDetail}>Tools: {listing.management_tools.join(' · ')}</Text>
            {listing.lock_reason ? <Text style={styles.lockText}>{listing.lock_reason}</Text> : null}

            <View style={styles.buttonRow}>
              <SecondaryButton
                label={isSelected ? 'Inspecting' : 'Inspect'}
                onPress={() => onInspectListing(listing.listing_id)}
              />
              <SecondaryButton
                label={compared ? 'Comparing' : 'Compare'}
                onPress={() => onToggleCompare(listing.listing_id)}
              />
              <PrimaryButton
                label={listing.buyable ? `Buy ${businessBuyLabel(listing)}` : 'Locked'}
                onPress={() => onBuyListing(listing)}
                disabled={buyDisabled}
              />
            </View>
          </View>
        );
      })}

      {comparedListings.length >= 2 ? (
        <View style={styles.compareBox}>
          <Text style={styles.sectionTitle}>Compare Shortlist</Text>
          {comparedListings.map((listing) => (
            <View key={listing.listing_id} style={styles.compareRow}>
              <Text style={styles.compareName}>{listing.listing_name}</Text>
              <Text style={styles.compareMeta}>
                {formatMoney(listing.price_xgp)} · Demand {listing.demand_score} · Traffic {listing.traffic_potential} · Employees {listing.employees}/{listing.employee_capacity}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function businessBuyLabel(listing: BusinessMarketListing): string {
  return listing.business_type === 'food_truck' ? 'Food Truck' : 'Fruit Shop';
}

const styles = StyleSheet.create({
  section: {
    gap: 10,
  },
  sectionTitle: {
    ...theme.typography.caption,
    color: theme.gameUi.primary,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  sectionBody: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
  },
  activeCard: {
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 14,
    backgroundColor: alpha(theme.gameUi.primary, 0.08),
    borderWidth: 1,
    borderColor: alpha(theme.gameUi.primary, 0.24),
    gap: 10,
  },
  activeTitle: {
    ...theme.typography.headingSm,
    color: theme.gameUi.textPrimary,
  },
  activeSubtitle: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
  },
  metricsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metricCard: {
    flex: 1,
    minWidth: 96,
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 10,
    backgroundColor: theme.ui.bg.sheet,
    borderWidth: 1,
    borderColor: theme.gameUi.cardBorder,
    gap: 4,
  },
  metricLabel: {
    ...theme.typography.caption,
    color: theme.gameUi.textSecondary,
    textTransform: 'uppercase',
  },
  metricValue: {
    ...theme.typography.bodyMd,
    color: theme.gameUi.textPrimary,
    fontWeight: '800',
  },
  metricMeta: {
    ...theme.typography.caption,
    color: theme.gameUi.textSecondary,
  },
  toolTitle: {
    ...theme.typography.caption,
    color: theme.gameUi.textSecondary,
    textTransform: 'uppercase',
  },
  toolBody: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textPrimary,
  },
  phaseHint: {
    ...theme.typography.bodySm,
    color: theme.gameUi.warning,
    fontWeight: '700',
  },
  listingCard: {
    borderRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: theme.ui.bg.sheet,
    borderWidth: 1,
    borderColor: theme.gameUi.cardBorder,
    gap: 8,
  },
  listingCardSelected: {
    borderColor: theme.gameUi.primary,
  },
  listingCardCompared: {
    borderColor: theme.gameUi.warning,
  },
  listingHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  listingTitleWrap: {
    flex: 1,
    gap: 2,
  },
  listingTitle: {
    ...theme.typography.bodyMd,
    color: theme.gameUi.textPrimary,
    fontWeight: '700',
  },
  listingMeta: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
  },
  listingPrice: {
    ...theme.typography.bodyMd,
    color: theme.gameUi.warning,
    fontWeight: '800',
  },
  metricPills: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  metricPill: {
    ...theme.typography.caption,
    color: theme.gameUi.textPrimary,
    backgroundColor: theme.ui.bg.sheet,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: theme.gameUi.cardBorder,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  listingDetail: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
  },
  lockText: {
    ...theme.typography.caption,
    color: theme.gameUi.warning,
  },
  buttonRow: {
    gap: 8,
  },
  compareBox: {
    borderRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: theme.ui.bg.sheet,
    borderWidth: 1,
    borderColor: theme.gameUi.cardBorder,
    gap: 8,
  },
  compareRow: {
    gap: 2,
  },
  compareName: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textPrimary,
    fontWeight: '700',
  },
  compareMeta: {
    ...theme.typography.caption,
    color: theme.gameUi.textSecondary,
  },
});

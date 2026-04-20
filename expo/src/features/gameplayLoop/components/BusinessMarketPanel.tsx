import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import Card from '@/components/ui/Card';
import Chip from '@/components/ui/Chip';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
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

function scoreChipVariant(score: number): 'positive' | 'warning' | 'danger' {
  if (score >= 78) return 'positive';
  if (score >= 58) return 'warning';
  return 'danger';
}

function listingCardVariant(options: { selected: boolean; compared: boolean }): 'default' | 'info' | 'warning' {
  if (options.selected) return 'info';
  if (options.compared) return 'warning';
  return 'default';
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
        <Card variant="info" style={styles.activeCard}>
          <Text style={styles.sectionTitle}>Active Business Growth</Text>
          <Text style={styles.activeTitle}>{activeBusinessProfile.display_name}</Text>
          <Text style={styles.activeSubtitle}>
            {activeBusinessProfile.growth_phase_label} | {activeBusinessProfile.location_label}
          </Text>

          <View style={styles.metricsRow}>
            <Card padded={false} style={styles.metricCard}>
              <Text style={styles.metricLabel}>Employees</Text>
              <Text style={styles.metricValue}>
                {activeBusinessProfile.employees}/{activeBusinessProfile.employee_capacity}
              </Text>
              <Text style={styles.metricMeta}>
                NPC {activeBusinessProfile.npc_employees} | Players {activeBusinessProfile.player_employees}
              </Text>
            </Card>
            <Card padded={false} style={styles.metricCard}>
              <Text style={styles.metricLabel}>Wages</Text>
              <Text style={styles.metricValue}>{formatMoney(activeBusinessProfile.wage_cost_xgp)}</Text>
              <Text style={styles.metricMeta}>Open slots {activeBusinessProfile.open_slots}</Text>
            </Card>
            <Card padded={false} style={styles.metricCard}>
              <Text style={styles.metricLabel}>Performance</Text>
              <Text style={styles.metricValue}>{activeBusinessProfile.performance_score}/100</Text>
              <View style={styles.metricChipRow}>
                <Chip
                  label={`Demand ${activeBusinessProfile.demand_score}/100`}
                  variant={scoreChipVariant(activeBusinessProfile.performance_score)}
                />
              </View>
            </Card>
          </View>

          <Text style={styles.toolTitle}>Management tools</Text>
          <Text style={styles.toolBody}>{activeBusinessProfile.management_tools.join(' | ')}</Text>
          <Text style={styles.phaseHint}>{activeBusinessProfile.phase_progress_label}</Text>

          <PrimaryButton
            label={activeBusinessProfile.next_phase_label ? `Advance To ${activeBusinessProfile.next_phase_label}` : 'Top Phase Reached'}
            onPress={activeBusinessProfile.next_phase_label ? onAdvancePhase : undefined}
            disabled={!activeBusinessProfile.next_phase_label}
          />
        </Card>
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
          <Card
            key={listing.listing_id}
            variant={listingCardVariant({ selected: isSelected, compared })}
            style={styles.listingCard}
          >
            <View style={styles.listingHeader}>
              <View style={styles.listingTitleWrap}>
                <Text style={styles.listingTitle}>{listing.listing_name}</Text>
                <Text style={styles.listingMeta}>
                  {listing.growth_phase_label} | {listing.location_label}
                </Text>
              </View>
              <Text style={styles.listingPrice}>{formatMoney(listing.price_xgp)}</Text>
            </View>

            <View style={styles.metricPills}>
              <Chip label={`Demand ${listing.demand_score}`} variant="neutral" />
              <Chip label={`Rep ${listing.reputation_score}`} variant="neutral" />
              <Chip label={`Traffic ${listing.traffic_potential}`} variant="neutral" />
              <Chip label={`Perf ${listing.performance_score}`} variant={scoreChipVariant(listing.performance_score)} />
            </View>

            <Text style={styles.listingDetail}>
              Employees {listing.employees}/{listing.employee_capacity} | Wage cost {formatMoney(listing.wage_cost_xgp)}
            </Text>
            <Text style={styles.listingDetail}>{listing.compare_note}</Text>
            <Text style={styles.listingDetail}>Tools: {listing.management_tools.join(' | ')}</Text>
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
          </Card>
        );
      })}

      {comparedListings.length >= 2 ? (
        <Card variant="warning" style={styles.compareBox}>
          <Text style={styles.compareTitle}>Compare Shortlist</Text>
          {comparedListings.map((listing) => (
            <View key={listing.listing_id} style={styles.compareRow}>
              <Text style={styles.compareName}>{listing.listing_name}</Text>
              <Text style={styles.compareMeta}>
                {formatMoney(listing.price_xgp)} | Demand {listing.demand_score} | Traffic {listing.traffic_potential} | Employees {listing.employees}/{listing.employee_capacity}
              </Text>
            </View>
          ))}
        </Card>
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
    color: theme.ui.text.onLight,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  sectionBody: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLightMuted,
  },
  activeCard: {
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  activeTitle: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onLight,
    fontWeight: '800',
  },
  activeSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLightMuted,
  },
  metricsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metricCard: {
    flex: 1,
    minWidth: 96,
    paddingHorizontal: 10,
    paddingVertical: 10,
    gap: 4,
  },
  metricLabel: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    textTransform: 'uppercase',
  },
  metricValue: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  metricMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
  metricChipRow: {
    marginTop: 2,
  },
  toolTitle: {
    ...theme.typography.caption,
    color: theme.ui.text.onLightMuted,
    textTransform: 'uppercase',
  },
  toolBody: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLight,
  },
  phaseHint: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLightMuted,
    fontWeight: '700',
  },
  listingCard: {
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
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
    color: theme.ui.text.onDark,
    fontWeight: '700',
  },
  listingMeta: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  listingPrice: {
    ...theme.typography.bodyMd,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  metricPills: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  listingDetail: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  lockText: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
    fontWeight: '700',
  },
  buttonRow: {
    gap: 8,
  },
  compareBox: {
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  compareRow: {
    gap: 2,
  },
  compareName: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDark,
    fontWeight: '700',
  },
  compareTitle: {
    ...theme.typography.caption,
    color: theme.ui.text.onDark,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  compareMeta: {
    ...theme.typography.caption,
    color: theme.ui.text.onDarkMuted,
  },
});

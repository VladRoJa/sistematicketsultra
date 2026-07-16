import {
  TrackForecastCenterBreakdownDimension,
  TrackForecastCenterCohort,
  TrackForecastCenterDrilldown,
  TrackForecastCenterScope,
} from '../../services/track.service';

export type TrackForecastCenterView = 'summary' | 'pace' | 'breakdown' | 'methodology';

export interface TrackForecastCenterNavigationEvent {
  drilldown: TrackForecastCenterDrilldown;
  sourceView: TrackForecastCenterView;
}

export interface TrackForecastCenterFilterState {
  trackDate: string;
  generationMode: 'manual_preview' | 'official_closed_day';
  scope: TrackForecastCenterScope;
  scopeId: string;
  cohort: TrackForecastCenterCohort;
  view: TrackForecastCenterView;
  breakdown: TrackForecastCenterBreakdownDimension;
}


// frontend\src\app\services\track.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type TrackGenerationMode = 'manual_preview' | 'official_closed_day';

export interface TrackPipelineRequest {
  track_date: string;
  generation_mode: TrackGenerationMode;
}

export interface TrackPipelineResult {
  status: string;
  track_date: string;
  generation_mode: TrackGenerationMode;
  refresh_dates: Record<string, string>;
  raw_ingestion: unknown;
  source_refresh_results: unknown;
  mart_refresh_result: {
    status: string;
    track_date: string;
    generation_mode: TrackGenerationMode;
    rows_inserted: number;
  };
}

export interface TrackPipelineResponse {
  status: 'ok' | 'error';
  result?: TrackPipelineResult;
  message?: string;
  detail?: string;
}

@Injectable({
  providedIn: 'root',
})
export class TrackService {
  private readonly baseUrl = 'http://localhost:5000/api/track';

  constructor(private readonly http: HttpClient) {}

  runDailyPipeline(
    trackDate: string,
    generationMode: TrackGenerationMode,
  ): Observable<TrackPipelineResponse> {
    const payload: TrackPipelineRequest = {
      track_date: trackDate,
      generation_mode: generationMode,
    };

    return this.http.post<TrackPipelineResponse>(
      `${this.baseUrl}/run-daily-pipeline`,
      payload,
    );
  }
}
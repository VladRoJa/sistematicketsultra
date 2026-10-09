import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface GoogleAdsOAuthStatus {
  enabled: boolean;
  authorized: boolean;
  customer_id?: string;
  last_authorized_at?: string | null;
  account_access_verified?: boolean;
}

export interface GoogleAdsAccount {
  customer_id: string;
  descriptive_name: string;
  currency_code: string;
  timezone: string;
  manager: boolean;
}

export interface GoogleAdsAccountCheck {
  account_access_verified: boolean;
  account: GoogleAdsAccount;
  directly_accessible_customer_ids: string[];
  target_directly_accessible: boolean;
  login_customer_id: string | null;
  api_version: string;
  mode: 'read_only';
  verified_live: boolean;
}

export interface GoogleAdsCampaignDailyRow {
  date: string;
  campaign_id: string;
  campaign_name: string;
  campaign_status: string;
  advertising_channel_type: string;
  impressions: number;
  clicks: number;
  cost_micros: number;
  cost: string;
  conversions: string;
}

export interface GoogleAdsCampaignDaily {
  account: GoogleAdsAccount;
  date_from: string;
  date_to: string;
  api_version: string;
  source: 'GOOGLE_ADS_API_LIVE';
  snapshot_persisted: false;
  totals: {
    impressions: number;
    clicks: number;
    cost_micros: number;
    cost: string;
    conversions: string;
  };
  conversions_note: string;
  rows: GoogleAdsCampaignDailyRow[];
}

export interface GoogleAdsApiError {
  code?: string;
}

export interface GoogleAdsConsentStart {
  authorization_url: string;
  expires_in_seconds: number;
}

@Injectable({ providedIn: 'root' })
export class GoogleAdsAdminService {
  private readonly base = `${environment.apiUrl}/integrations/google-ads`;

  constructor(private readonly http: HttpClient) {}

  getStatus(): Observable<GoogleAdsOAuthStatus> {
    return this.http.get<GoogleAdsOAuthStatus>(`${this.base}/oauth/status`);
  }

  startAuthorization(): Observable<GoogleAdsConsentStart> {
    // Same-origin Secure HttpOnly nonce cookie binds OAuth callback to this browser.
    // Existing auth interceptor supplies JWT from SessionService.
    return this.http.post<GoogleAdsConsentStart>(
      `${this.base}/oauth/start`,
      {},
      { withCredentials: true }
    );
  }

  checkAccount(): Observable<GoogleAdsAccountCheck> {
    return this.http.get<GoogleAdsAccountCheck>(`${this.base}/account-check`);
  }

  getCampaignDaily(dateFrom: string, dateTo: string): Observable<GoogleAdsCampaignDaily> {
    const params = new HttpParams()
      .set('date_from', dateFrom)
      .set('date_to', dateTo);
    return this.http.get<GoogleAdsCampaignDaily>(
      `${this.base}/campaign-daily`,
      { params }
    );
  }
}

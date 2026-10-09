import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

export type SystemDailyCheckAnswerValue = 'YES' | 'NO' | 'NA';
export type SystemDailyCheckGeneralStatus =
  | 'NORMAL'
  | 'MINOR_FAILURE'
  | 'OPERATIONAL_IMPACT';
export type SystemDailyCheckAffectedScope = 'ONE' | 'MULTIPLE';

export interface SystemDailyCheckQuestion {
  question_key: string;
  label: string;
  category_key: string;
  requires_affected_scope: boolean;
}

export interface SystemDailyCheckStatus {
  eligible: boolean;
  sucursal_id: number;
  business_date: string;
  completed: boolean;
  check_id: number | null;
  postpone_count: number;
  can_postpone: boolean;
  should_prompt: boolean;
  mandatory: boolean;
  next_prompt_at: string | null;
  mandatory_from_at: string | null;
  completed_at: string | null;
}

export interface SystemDailyCheckBranch {
  sucursal_id: number;
  sucursal: string;
  serie?: string | null;
  operational_status?: string | null;
  is_demo?: boolean;
}

export interface SystemDailyCheckBranchCatalog {
  branches: SystemDailyCheckBranch[];
  preferred_branch_id: number | null;
}

export interface SystemDailyCheckIssuePayload {
  affected_scope?: SystemDailyCheckAffectedScope | null;
  reported_to_support: boolean;
  description: string;
}

export interface SystemDailyCheckAnswerPayload {
  question_key: string;
  answer: SystemDailyCheckAnswerValue;
  issue?: SystemDailyCheckIssuePayload;
}

export interface SystemDailyCheckSubmitPayload {
  answers: SystemDailyCheckAnswerPayload[];
  general_status: SystemDailyCheckGeneralStatus;
}

export interface SystemDailyCheckSubmitResponse {
  id: number;
  sucursal_id: number;
  business_date: string;
  performed_by_user_id: number;
  general_status: SystemDailyCheckGeneralStatus;
  submitted_at: string | null;
}

@Injectable({ providedIn: 'root' })
export class SystemDailyCheckService {
  private readonly apiUrl = `${environment.apiUrl}/system-daily-checks`;

  constructor(private http: HttpClient) {}

  getQuestions(): Observable<{
    eligible: boolean;
    questions: SystemDailyCheckQuestion[];
  }> {
    return this.http.get<{
      eligible: boolean;
      questions: SystemDailyCheckQuestion[];
    }>(`${this.apiUrl}/questions`);
  }

  getBranches(): Observable<SystemDailyCheckBranchCatalog> {
    return this.http.get<SystemDailyCheckBranchCatalog>(
      `${this.apiUrl}/branches`,
    );
  }

  getTodayStatus(
    branchId: number,
  ): Observable<SystemDailyCheckStatus> {
    return this.http.get<SystemDailyCheckStatus>(
      `${this.apiUrl}/today/status`,
      {
        params: this.branchParams(branchId),
      },
    );
  }

  postponeToday(
    branchId: number,
  ): Observable<SystemDailyCheckStatus> {
    return this.http.post<SystemDailyCheckStatus>(
      `${this.apiUrl}/today/postpone`,
      {},
      {
        params: this.branchParams(branchId),
      },
    );
  }

  submitToday(
    branchId: number,
    payload: SystemDailyCheckSubmitPayload,
    evidenceByQuestion: ReadonlyMap<string, File | null>,
  ): Observable<SystemDailyCheckSubmitResponse> {
    const evidenceEntries = Array.from(
      evidenceByQuestion.entries(),
    ).filter(([, file]) => file instanceof File);

    if (evidenceEntries.length === 0) {
      return this.http.post<SystemDailyCheckSubmitResponse>(
        `${this.apiUrl}/today/submit`,
        payload,
        {
          params: this.branchParams(branchId),
        },
      );
    }

    const formData = new FormData();
    formData.append('payload', JSON.stringify(payload));

    for (const [questionKey, file] of evidenceEntries) {
      if (!file) {
        continue;
      }
      formData.append(
        `evidence__${questionKey}`,
        file,
        file.name,
      );
    }

    return this.http.post<SystemDailyCheckSubmitResponse>(
      `${this.apiUrl}/today/submit`,
      formData,
      {
        params: this.branchParams(branchId),
      },
    );
  }

  private branchParams(branchId: number): HttpParams {
    return new HttpParams().set(
      'sucursal_id',
      String(branchId),
    );
  }
}

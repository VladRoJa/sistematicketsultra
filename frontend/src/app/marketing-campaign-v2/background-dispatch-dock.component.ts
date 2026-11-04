import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { interval, Subscription } from 'rxjs';
import { AuthService } from '../services/auth.service';
import {
  BackgroundDispatchJob, backgroundDispatchLabel, backgroundDispatchProgress,
  visibleBackgroundJobs,
} from './background-dispatch.model';
import { BackgroundDispatchActivityService } from './background-dispatch-activity.service';
import { loadDismissedBackgroundJobIds, persistDismissedBackgroundJobIds } from './background-dispatch-dock-visibility';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';
import { MarketingCampaignV2GovernedConsoleDialogComponent } from './marketing-campaign-v2-governed-console-dialog.component';

@Component({
  selector: 'app-campaign-v2-background-dock',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  templateUrl: './background-dispatch-dock.component.html',
  styleUrls: ['./background-dispatch-dock.component.css'],
})
export class BackgroundDispatchDockComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly activity = inject(BackgroundDispatchActivityService);
  private readonly dialog = inject(MatDialog);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private request: Subscription | null = null;
  private pollingForbidden = false;
  private initialIdentity = '';

  jobs: BackgroundDispatchJob[] = [];
  stale = false;
  private dismissedJobIds = new Set<number>();
  readonly label = backgroundDispatchLabel;
  readonly progress = backgroundDispatchProgress;

  ngOnInit(): void {
    const account = this.auth.getUser();
    this.initialIdentity = String(account?.username || '').trim().toUpperCase();
    // The backend GET is the authority for dispatch permissions. Avoid
    // duplicating role allowlists that can hide an authorized operator's job.
    if (!this.initialIdentity) return;
    this.dismissedJobIds = loadDismissedBackgroundJobIds(this.initialIdentity);
    this.refresh();
    interval(10000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.refresh());
    this.activity.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.refresh());
    this.destroyRef.onDestroy(() => this.request?.unsubscribe());
  }

  dismissDock(): void {
    // Deactivate these specific alerts, not the dispatch jobs. New jobs can
    // still appear, and dismissals survive polling, navigation and page reloads.
    if (!this.initialIdentity || this.currentIdentity() !== this.initialIdentity) return;
    this.dismissedJobIds = persistDismissedBackgroundJobIds(
      this.initialIdentity, this.dismissedJobIds, this.jobs.map(job => job.job_id),
    );
    this.jobs = this.jobs.filter(job => !this.dismissedJobIds.has(job.job_id));
  }

  private currentIdentity(): string {
    return String(this.auth.getUser()?.username || '').trim().toUpperCase();
  }

  refresh(): void {
    if (!this.initialIdentity || this.currentIdentity() !== this.initialIdentity) {
      this.pollingForbidden = true;
      this.jobs = [];
      this.request?.unsubscribe();
      return;
    }
    if (this.pollingForbidden || (this.request && !this.request.closed)) return;
    this.request = this.api.listMyBackgroundJobs().subscribe({
      next: response => {
        // A request may finish after account replacement: never expose previous data.
        if (this.currentIdentity() !== this.initialIdentity) {
          this.pollingForbidden = true;
          this.jobs = [];
          return;
        }
        this.stale = false;
        this.jobs = visibleBackgroundJobs(response.jobs, Date.now())
          .filter(job => !this.dismissedJobIds.has(job.job_id));
      },
      error: (error: HttpErrorResponse) => {
        if ([401, 403, 404].includes(error.status)) {
          this.pollingForbidden = true;
          this.jobs = [];
        } else {
          this.stale = true;
        }
      },
    });
  }

  open(job: BackgroundDispatchJob): void {
    if (this.pollingForbidden || this.currentIdentity() !== this.initialIdentity) return;
    const alreadyOpen = this.dialog.openDialogs.some(ref =>
      ref.componentInstance instanceof MarketingCampaignV2GovernedConsoleDialogComponent &&
      ref.componentInstance.data.campaignId === job.campaign_id);
    if (alreadyOpen) return;
    const ref = this.dialog.open(MarketingCampaignV2GovernedConsoleDialogComponent, {
      width: 'min(1200px, 96vw)', maxWidth: '96vw', maxHeight: '95vh',
      disableClose: true, autoFocus: false, panelClass: 'campaign-v2-admin-dialog',
      data: { campaignId: job.campaign_id, campaignName: `Campaña #${job.campaign_id}`,
              jobId: job.job_id },
    });
    ref.afterClosed().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.refresh());
  }
}

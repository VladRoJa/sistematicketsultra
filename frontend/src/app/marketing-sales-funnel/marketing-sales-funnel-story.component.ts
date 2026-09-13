import { CommonModule } from '@angular/common';
import { Component, Input, inject } from '@angular/core';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  MarketingSalesFunnelMetrics,
  MarketingSalesOriginBreakdown,
} from './marketing-sales-funnel.models';
import {
  MarketingSalesFunnelDetailDialogComponent,
} from './marketing-sales-funnel-detail-dialog.component';


interface FunnelNodeView {
  step: string;
  label: string;
  value: string;
  share: string;
  metric: string;
  icon: string;
  origin?: string;
}

interface IventasStageView {
  step: string;
  label: string;
  value: string;
  metric: string;
  icon: string;
}

interface FallbackOriginView extends MarketingSalesOriginBreakdown {
  displayLabel: string;
  salesDisplay: string;
  shareDisplay: string;
  icon: string;
}


@Component({
  selector: 'app-marketing-sales-funnel-story',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: './marketing-sales-funnel-story.component.html',
  styleUrls: ['./marketing-sales-funnel-story.component.css'],
})
export class MarketingSalesFunnelStoryComponent {
  private readonly dialog = inject(MatDialog);

  @Input({ required: true }) month = '';
  @Input({ required: true }) summary: MarketingSalesFunnelMetrics | null = null;
  @Input() reconciliationLabel = '';

  get saleNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) {
      return null;
    }
    return this.createNode(
      '01',
      'Venta Nueva',
      summary.sales_total,
      summary.sales_total,
      'sales_total',
      'groups',
    );
  }

  get iventasNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) {
      return null;
    }
    return this.createNode(
      '02',
      'Con Match iVentas',
      summary.sales_iventas,
      summary.sales_total,
      'sales_iventas',
      'link',
    );
  }

  get fallbackNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) {
      return null;
    }
    return this.createNode(
      '08',
      'Sin Match iVentas',
      summary.sales_not_iventas,
      summary.sales_total,
      'sales_not_iventas',
      'person',
    );
  }

  get publicationNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) {
      return null;
    }
    return this.createNode(
      '06',
      'Venta por publicaciones',
      summary.sales_iventas_meta,
      summary.sales_total,
      'sales_iventas_meta',
      'campaign',
    );
  }

  get organicNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) {
      return null;
    }
    return this.createNode(
      '07',
      'Orgánico',
      summary.sales_iventas_other,
      summary.sales_total,
      'origin',
      'eco',
      'IVENTAS_OTHER',
    );
  }

  get iventasStages(): IventasStageView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    return [
      {
        step: '03',
        label: 'Leads iVentas',
        value: this.formatInteger(summary.iventas_contacts),
        metric: 'leads_meta',
        icon: 'person',
      },
      {
        step: '04',
        label: 'Visitas iVentas',
        value: this.formatInteger(summary.visits_iventas),
        metric: 'visits_iventas',
        icon: 'event',
      },
      {
        step: '05',
        label: 'Ventas iVentas',
        value: this.formatInteger(summary.sales_iventas),
        metric: 'sales_iventas',
        icon: 'leaderboard',
      },
    ];
  }

  get fallbackOrigins(): FallbackOriginView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    return summary.origin_breakdown
      .filter((origin) => (
        origin.sales > 0
        && origin.key !== 'IVENTAS_META'
        && origin.key !== 'IVENTAS_OTHER'
      ))
      .map((origin) => ({
        ...origin,
        displayLabel: this.resolveOriginLabel(origin),
        salesDisplay: this.formatInteger(origin.sales),
        shareDisplay: this.formatPercent(
          summary.sales_not_iventas > 0
            ? origin.sales / summary.sales_not_iventas
            : null,
        ),
        icon: this.resolveOriginIcon(origin.key),
      }))
      .sort((left, right) => right.sales - left.sales);
  }

  get narrative(): string {
    const summary = this.summary;
    if (!summary) {
      return '';
    }

    return `${this.formatInteger(summary.sales_iventas)} pasaron por iVentas · ${this.formatInteger(summary.sales_not_iventas)} por fallback`;
  }

  openNode(node: FunnelNodeView | null): void {
    if (!node) {
      return;
    }
    this.openDetail(node.metric, node.origin);
  }

  openStage(stage: IventasStageView): void {
    this.openDetail(stage.metric);
  }

  openOrigin(origin: FallbackOriginView): void {
    this.openDetail('origin', origin.key);
  }

  private openDetail(metric: string, origin?: string): void {
    if (!this.month || !metric) {
      return;
    }

    this.dialog.open(MarketingSalesFunnelDetailDialogComponent, {
      data: {
        month: this.month,
        metric,
        origin,
      },
      width: '96vw',
      maxWidth: '1600px',
      height: '88vh',
      maxHeight: '920px',
      autoFocus: false,
      restoreFocus: true,
    });
  }

  private createNode(
    step: string,
    label: string,
    value: number,
    total: number,
    metric: string,
    icon: string,
    origin?: string,
  ): FunnelNodeView {
    return {
      step,
      label,
      value: this.formatInteger(value),
      share: this.formatPercent(total > 0 ? value / total : null),
      metric,
      icon,
      origin,
    };
  }

  private resolveOriginLabel(origin: MarketingSalesOriginBreakdown): string {
    if (origin.key === 'OTHER_SURVEY') {
      return 'Visita a Plaza Comercial';
    }
    if (origin.key === 'UNKNOWN') {
      return 'Sin identificar';
    }
    return origin.label;
  }

  private resolveOriginIcon(originKey: string): string {
    const icons: Record<string, string> = {
      SOCIAL_UNTRACED: 'alternate_email',
      REFERRAL: 'groups',
      PROXIMITY: 'location_on',
      PLAZA: 'storefront',
      OFFLINE: 'description',
      OTHER_SURVEY: 'storefront',
      UNKNOWN: 'help_outline',
    };
    return icons[originKey] || 'label';
  }

  private formatInteger(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  private formatPercent(value: number | null): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }
}

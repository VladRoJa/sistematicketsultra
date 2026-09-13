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
  label: string;
  value: string;
  support: string;
  metric: string;
  icon: string;
  origin?: string;
  tone: 'orange' | 'gray';
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
  imports: [CommonModule, MatDialogModule, MatIconModule],
  templateUrl: './marketing-sales-funnel-story.component.html',
  styleUrls: ['./marketing-sales-funnel-story.component.css'],
})
export class MarketingSalesFunnelStoryComponent {
  private readonly dialog = inject(MatDialog);

  @Input({ required: true }) month = '';
  @Input({ required: true }) summary: MarketingSalesFunnelMetrics | null | undefined = null;
  @Input() reconciliationLabel = '';

  get narrative(): string {
    const summary = this.summary;
    if (!summary) {
      return '';
    }

    return `Dos recorridos convergen en ${this.formatInteger(summary.sales_iventas)} ventas iVentas; las ${this.formatInteger(summary.sales_not_iventas)} restantes continúan por clasificación de origen.`;
  }

  get leadsNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Leads iVentas',
      summary.leads_iventas || 0,
      'Creados en el mes con conversación iniciada',
      'leads_iventas',
      'person',
      'orange',
    );
  }

  get visitsNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Visitas iVentas',
      summary.visits_iventas,
      'Visitas que cruzan por teléfono con iVentas',
      'visits_iventas',
      'event',
      'orange',
    );
  }

  get salesTotalNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Venta Nueva',
      summary.sales_total,
      '100% del universo de Venta Nueva',
      'sales_total',
      'groups',
      'orange',
    );
  }

  get salesIventasNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Ventas iVentas',
      summary.sales_iventas,
      `${this.formatPercent(summary.sales_total > 0 ? summary.sales_iventas / summary.sales_total : null)} de Venta Nueva · punto de unión`,
      'sales_iventas',
      'leaderboard',
      'orange',
    );
  }

  get publicationNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Venta por publicaciones',
      summary.sales_iventas_meta,
      `${this.formatPercent(summary.sales_total > 0 ? summary.sales_iventas_meta / summary.sales_total : null)} del total`,
      'sales_iventas_meta',
      'campaign',
      'orange',
    );
  }

  get organicNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Orgánico',
      summary.sales_iventas_other,
      'Entró a iVentas sin publicidad pagada',
      'origin',
      'eco',
      'orange',
      'IVENTAS_OTHER',
    );
  }

  get fallbackNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Sin Match iVentas',
      summary.sales_not_iventas,
      `${this.formatPercent(summary.sales_total > 0 ? summary.sales_not_iventas / summary.sales_total : null)} de Venta Nueva`,
      'sales_not_iventas',
      'person',
      'gray',
    );
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

  openNode(node: FunnelNodeView | null): void {
    if (!node) return;
    this.openDetail(node.metric, node.origin);
  }

  openOrigin(origin: FallbackOriginView): void {
    this.openDetail('origin', origin.key);
  }

  private createNode(
    label: string,
    value: number,
    support: string,
    metric: string,
    icon: string,
    tone: 'orange' | 'gray',
    origin?: string,
  ): FunnelNodeView {
    return {
      label,
      value: this.formatInteger(value),
      support,
      metric,
      icon,
      tone,
      origin,
    };
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

  private resolveOriginLabel(origin: MarketingSalesOriginBreakdown): string {
    if (origin.key === 'OTHER_SURVEY') {
      return 'Visita a Plaza Comercial';
    }
    if (origin.key === 'UNKNOWN') {
      return 'Venta por web';
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
      UNKNOWN: 'language',
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

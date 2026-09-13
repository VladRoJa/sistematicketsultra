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

interface FlowRibbonView {
  id: string;
  d: string;
  tone: 'orange' | 'gray';
  opacity: number;
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
  @Input() branchIds: number[] = [];

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
      summary.leads_meta,
      'First message + tag Meta/FB en el snapshot canónico',
      'leads_meta',
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

  get flowRibbons(): FlowRibbonView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    const leads = summary.leads_meta;
    const visits = summary.visits_iventas;
    const salesIventas = summary.sales_iventas;
    const salesTotal = summary.sales_total;
    const salesFallback = summary.sales_not_iventas;
    const publications = summary.sales_iventas_meta;
    const organic = summary.sales_iventas_other;

    const leadReference = Math.max(leads, visits, 1);
    const iventasReference = Math.max(visits, salesIventas, 1);
    const salesReference = Math.max(salesTotal, 1);
    const outputReference = Math.max(salesIventas, 1);

    return [
      this.createRibbon({
        id: 'leads-visits',
        sourceX: 245,
        sourceY: 120,
        targetX: 330,
        targetY: 120,
        sourceThickness: this.ribbonThickness(leads, leadReference, 18, 70),
        targetThickness: this.ribbonThickness(visits, leadReference, 14, 70),
        tone: 'orange',
        opacity: 0.20,
      }),
      this.createRibbon({
        id: 'visits-sales',
        sourceX: 560,
        sourceY: 120,
        targetX: 620,
        targetY: 270,
        sourceThickness: this.ribbonThickness(visits, iventasReference, 16, 60),
        targetThickness: this.ribbonThickness(salesIventas, iventasReference, 16, 60),
        tone: 'orange',
        opacity: 0.22,
      }),
      this.createRibbon({
        id: 'sales-total-iventas',
        sourceX: 300,
        sourceY: 350,
        targetX: 620,
        targetY: 305,
        sourceThickness: this.ribbonThickness(salesIventas, salesReference, 18, 72),
        targetThickness: this.ribbonThickness(salesIventas, salesReference, 18, 72),
        tone: 'orange',
        opacity: 0.24,
      }),
      this.createRibbon({
        id: 'sales-total-fallback',
        sourceX: 300,
        sourceY: 430,
        targetX: 430,
        targetY: 550,
        sourceThickness: this.ribbonThickness(salesFallback, salesReference, 18, 72),
        targetThickness: this.ribbonThickness(salesFallback, salesReference, 18, 72),
        tone: 'gray',
        opacity: 0.24,
      }),
      this.createRibbon({
        id: 'fallback-origins',
        sourceX: 650,
        sourceY: 550,
        targetX: 900,
        targetY: 570,
        sourceThickness: this.ribbonThickness(salesFallback, salesReference, 18, 52),
        targetThickness: this.ribbonThickness(salesFallback, salesReference, 18, 44),
        tone: 'gray',
        opacity: 0.18,
      }),
      this.createRibbon({
        id: 'iventas-publications',
        sourceX: 820,
        sourceY: 260,
        targetX: 960,
        targetY: 120,
        sourceThickness: this.ribbonThickness(publications, outputReference, 14, 58),
        targetThickness: this.ribbonThickness(publications, outputReference, 14, 58),
        tone: 'orange',
        opacity: 0.22,
      }),
      this.createRibbon({
        id: 'iventas-organic',
        sourceX: 820,
        sourceY: 330,
        targetX: 960,
        targetY: 360,
        sourceThickness: this.ribbonThickness(organic, outputReference, 14, 58),
        targetThickness: this.ribbonThickness(organic, outputReference, 14, 58),
        tone: 'orange',
        opacity: 0.22,
      }),
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

  private createRibbon(config: {
    id: string;
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    sourceThickness: number;
    targetThickness: number;
    tone: 'orange' | 'gray';
    opacity: number;
  }): FlowRibbonView {
    const horizontalDistance = Math.max(40, config.targetX - config.sourceX);
    const controlOffset = horizontalDistance * 0.46;

    const sourceTop = config.sourceY - (config.sourceThickness / 2);
    const sourceBottom = config.sourceY + (config.sourceThickness / 2);
    const targetTop = config.targetY - (config.targetThickness / 2);
    const targetBottom = config.targetY + (config.targetThickness / 2);

    const sourceControlX = config.sourceX + controlOffset;
    const targetControlX = config.targetX - controlOffset;

    const d = [
      `M ${config.sourceX} ${sourceTop}`,
      `C ${sourceControlX} ${sourceTop}, ${targetControlX} ${targetTop}, ${config.targetX} ${targetTop}`,
      `L ${config.targetX} ${targetBottom}`,
      `C ${targetControlX} ${targetBottom}, ${sourceControlX} ${sourceBottom}, ${config.sourceX} ${sourceBottom}`,
      'Z',
    ].join(' ');

    return {
      id: config.id,
      d,
      tone: config.tone,
      opacity: config.opacity,
    };
  }

  private ribbonThickness(
    value: number,
    reference: number,
    minimum: number,
    maximum: number,
  ): number {
    if (value <= 0 || reference <= 0) {
      return minimum;
    }

    const ratio = Math.min(1, Math.max(0.06, value / reference));
    return minimum + ((maximum - minimum) * Math.sqrt(ratio));
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
        branchIds: this.branchIds,
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

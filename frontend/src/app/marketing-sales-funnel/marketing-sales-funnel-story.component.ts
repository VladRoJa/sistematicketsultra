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

interface SaleCompositionChildView {
  label: string;
  value: string;
  icon: string;
  metric: string;
}

interface SaleCompositionView {
  total: string;
  totalMetric: string;
  digitalTotal: string;
  digitalShare: string;
  digitalMetric: string;
  digitalChildren: SaleCompositionChildView[];
  webTotal: string;
  webShare: string;
  webMetric: string;
  btlTotal: string;
  btlShare: string;
  btlMetric: string;
  btlOrigins: FallbackOriginView[];
}
interface ConversionKpiView {
  label: string;
  value: string;
}

interface VisitBranchView {
  key: 'iventas' | 'untraced';
  label: string;
  value: string;
  metric: string;
  icon: string;
  tone: 'orange' | 'gray';
  share: string;
  bought: string;
  boughtMetric: string;
  boughtShare: string;
  notBought: string;
  notBoughtMetric: string;
  notBoughtShare: string;
}

interface FunnelExecutiveSummaryView {
  investment_display: string;
  lead_to_visit_display: string;
  visit_to_digital_sale_display: string;
  lead_to_sale_display: string;
  cpl_display: string;
  cpt_display: string;
  cac_display: string;
}
interface SaleChannelView {
  key: 'digital' | 'organic' | 'web' | 'btl' | 'total';
  label: string;
  value: string;
  metric: string;
}

@Component({
  selector: 'app-marketing-sales-funnel-story',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatIconModule],
  templateUrl: './marketing-sales-funnel-story.component.html',
  styleUrls: [
    './marketing-sales-funnel-story.component.css',
    './marketing-sales-funnel-story-visit-conversion.component.css',
  ],
})
export class MarketingSalesFunnelStoryComponent {
  private readonly dialog = inject(MatDialog);

  @Input({ required: true }) month = '';
  @Input() cutoffDate: string | null = null;
  @Input({ required: true }) summary: MarketingSalesFunnelMetrics | null | undefined = null;
  @Input() reconciliationLabel = '';
  @Input() branchIds: number[] = [];
  @Input() executiveSummary: FunnelExecutiveSummaryView | null = null;

  get narrative(): string {
    const summary = this.summary;
    if (!summary) {
      return '';
    }

    return `El CRM aporta ${this.formatInteger(summary.sales_iventas)} ventas; las ${this.formatInteger(summary.sales_not_iventas)} restantes continúan fuera del CRM por clasificación de origen.`;
  }

  get leadsNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Leads CRM',
      summary.leads_iventas,
      'Contactos que iniciaron conversación en el CRM',
      'leads_iventas',
      'person',
      'orange',
    );
  }

  get visitsTotalNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Visitas',
      summary.visits_total,
      'Visitas registradas y compras directas de Venta Nueva',
      'visits_total',
      'storefront',
      'orange',
    );
  }

  get visitBranches(): VisitBranchView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    return [
      {
        key: 'iventas',
        label: 'CRM',
        value: this.formatInteger(summary.visits_iventas),
        metric: 'visits_iventas',
        icon: 'smartphone',
        tone: 'orange',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_iventas / summary.visits_total
            : null,
        ),
        bought: this.formatInteger(summary.visits_iventas_bought),
        boughtMetric: 'visits_iventas_bought',
        boughtShare: this.formatPercent(
          summary.visits_iventas > 0
            ? summary.visits_iventas_bought / summary.visits_iventas
            : null,
        ),
        notBought: this.formatInteger(summary.visits_iventas_not_bought),
        notBoughtMetric: 'visits_iventas_not_bought',
        notBoughtShare: this.formatPercent(
          summary.visits_iventas > 0
            ? summary.visits_iventas_not_bought / summary.visits_iventas
            : null,
        ),
      },
      {
        key: 'untraced',
        label: 'Organicas',
        value: this.formatInteger(summary.visits_not_iventas),
        metric: 'visits_not_iventas',
        icon: 'link_off',
        tone: 'gray',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_not_iventas / summary.visits_total
            : null,
        ),
        bought: this.formatInteger(summary.visits_not_iventas_bought),
        boughtMetric: 'visits_not_iventas_bought',
        boughtShare: this.formatPercent(
          summary.visits_not_iventas > 0
            ? summary.visits_not_iventas_bought / summary.visits_not_iventas
            : null,
        ),
        notBought: this.formatInteger(summary.visits_not_iventas_not_bought),
        notBoughtMetric: 'visits_not_iventas_not_bought',
        notBoughtShare: this.formatPercent(
          summary.visits_not_iventas > 0
            ? summary.visits_not_iventas_not_bought / summary.visits_not_iventas
            : null,
        ),
      },
    ];
  }

  get visitsNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Visitas CRM',
      summary.visits_iventas,
      '',
      'visits_iventas',
      'smartphone',
      'orange',
    );
  }

  get untracedVisitsNode(): FunnelNodeView | null {
    const summary = this.summary;
    if (!summary) return null;

    return this.createNode(
      'Visitas fuera CRM',
      summary.visits_not_iventas,
      '',
      'visits_not_iventas',
      'link_off',
      'gray',
    );
  }

  get saleChannelBreakdown(): SaleChannelView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    return [
      {
        key: 'digital',
        label: 'Venta digital',
        value: this.formatInteger(summary.sales_digital),
        metric: 'sales_digital',
      },
      {
        key: 'organic',
        label: 'Orgánica digital',
        value: this.formatInteger(summary.sales_digital_organic),
        metric: 'sales_digital_organic',
      },
      {
        key: 'web',
        label: 'Web',
        value: this.formatInteger(summary.sales_web),
        metric: 'sales_web',
      },
      {
        key: 'btl',
        label: 'BTL',
        value: this.formatInteger(summary.sales_btl),
        metric: 'sales_btl',
      },
      {
        key: 'total',
        label: 'Total',
        value: this.formatInteger(summary.sales_total),
        metric: 'sales_total',
      },
    ];
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
      'Ventas CRM',
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
      'CRM sin publicidad',
      summary.sales_iventas_other,
      'Ventas CRM sin origen publicitario identificado',
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
      'Fuera CRM',
      summary.sales_not_iventas,
      `${this.formatPercent(summary.sales_total > 0 ? summary.sales_not_iventas / summary.sales_total : null)} de Venta Nueva`,
      'sales_not_iventas',
      'person',
      'gray',
    );
  }

  get conversionKpis(): ConversionKpiView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    return [
      {
        label: 'Lead CRM → Visita CRM',
        value: this.formatPercent(
          summary.leads_iventas > 0
            ? summary.visits_iventas / summary.leads_iventas
            : null,
        ),
      },
      {
        label: 'Visita CRM → Compra',
        value: this.formatPercent(summary.iventas_visit_conversion_rate),
      },
      {
        label: 'Visita fuera CRM → Compra',
        value: this.formatPercent(summary.not_iventas_visit_conversion_rate),
      },
      {
        label: 'Venta Nueva → Venta CRM',
        value: this.formatPercent(summary.iventas_sale_share),
      },
    ];
  }

  get flowRibbons(): FlowRibbonView[] {
    const summary = this.summary;
    if (!summary) {
      return [];
    }

    const leads = summary.leads_meta;
    const visits = summary.visits_iventas;
    const visitsIventasBought = summary.visits_iventas_bought;
    const visitsNotIventasBought = summary.visits_not_iventas_bought;
    const salesIventas = summary.sales_iventas;
    const salesTotal = summary.sales_total;
    const salesFallback = summary.sales_not_iventas;
    const publications = summary.sales_iventas_meta;
    const organic = summary.sales_iventas_other;

    const leadReference = Math.max(leads, visits, 1);
    const conversionReference = Math.max(
      visitsIventasBought,
      visitsNotIventasBought,
      1,
    );
    const salesReference = Math.max(salesTotal, 1);
    const outputReference = Math.max(salesIventas, 1);

    return [
      this.createRibbon({
        id: 'leads-visits',
        sourceX: 135,
        sourceY: 96,
        targetX: 220,
        targetY: 96,
        sourceThickness: this.ribbonThickness(leads, leadReference, 18, 70),
        targetThickness: this.ribbonThickness(visits, leadReference, 14, 70),
        tone: 'orange',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.20,
      }),
      this.createRibbon({
        id: 'visits-iventas-sales',
        sourceX: 305,
        sourceY: 138,
        targetX: 420,
        targetY: 145,
        sourceThickness: this.ribbonThickness(
          visitsIventasBought,
          conversionReference,
          10,
          28,
        ),
        targetThickness: this.ribbonThickness(
          visitsIventasBought,
          conversionReference,
          10,
          28,
        ),
        tone: 'orange',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.24,
      }),
      this.createRibbon({
        id: 'sales-total-iventas',
        sourceX: 305,
        sourceY: 305,
        targetX: 420,
        targetY: 185,
        sourceThickness: this.ribbonThickness(salesIventas, salesReference, 18, 72),
        targetThickness: this.ribbonThickness(salesIventas, salesReference, 18, 72),
        tone: 'orange',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.24,
      }),
      this.createRibbon({
        id: 'sales-total-fallback',
        sourceX: 288,
        sourceY: 395,
        targetX: 410,
        targetY: 490,
        sourceThickness: this.ribbonThickness(salesFallback, salesReference, 18, 72),
        targetThickness: this.ribbonThickness(salesFallback, salesReference, 18, 72),
        tone: 'gray',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_not_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.24,
      }),
      this.createRibbon({
        id: 'untraced-visits-fallback',
        sourceX: 245,
        sourceY: 585,
        targetX: 410,
        targetY: 505,
        sourceThickness: this.ribbonThickness(
          visitsNotIventasBought,
          conversionReference,
          10,
          28,
        ),
        targetThickness: this.ribbonThickness(
          visitsNotIventasBought,
          conversionReference,
          10,
          28,
        ),
        tone: 'gray',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_not_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.24,
      }),
      this.createRibbon({
        id: 'fallback-origins',
        sourceX: 575,
        sourceY: 490,
        targetX: 625,
        targetY: 490,
        sourceThickness: this.ribbonThickness(salesFallback, salesReference, 18, 52),
        targetThickness: this.ribbonThickness(salesFallback, salesReference, 18, 44),
        tone: 'gray',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_not_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.18,
      }),
      this.createRibbon({
        id: 'iventas-publications',
        sourceX: 575,
        sourceY: 126,
        targetX: 700,
        targetY: 82,
        sourceThickness: this.ribbonThickness(publications, outputReference, 14, 58),
        targetThickness: this.ribbonThickness(publications, outputReference, 14, 58),
        tone: 'orange',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.22,
      }),
      this.createRibbon({
        id: 'iventas-organic',
        sourceX: 575,
        sourceY: 186,
        targetX: 700,
        targetY: 214,
        sourceThickness: this.ribbonThickness(organic, outputReference, 14, 58),
        targetThickness: this.ribbonThickness(organic, outputReference, 14, 58),
        tone: 'orange',
        share: this.formatPercent(
          summary.visits_total > 0
            ? summary.visits_iventas / summary.visits_total
            : null,
        ),
        opacity: 0.22,
      }),
    ];
  }

  get saleComposition(): SaleCompositionView | null {
    const summary = this.summary;

    if (!summary) {
      return null;
    }

    const digitalTotal =
      summary.sales_digital + summary.sales_digital_organic;

    const btlOrigins = (summary.btl_origin_breakdown ?? [])
      .filter((origin) => origin.sales > 0)
      .map((origin) => ({
        ...origin,
        displayLabel: origin.label,
        salesDisplay: this.formatInteger(origin.sales),
        shareDisplay: this.formatPercent(
          summary.sales_btl > 0
            ? origin.sales / summary.sales_btl
            : null,
        ),
        icon: this.resolveOriginIcon(origin.key),
      }))
      .sort((left, right) => right.sales - left.sales);

    return {
      total: this.formatInteger(summary.sales_total),
      totalMetric: 'sales_total',
      digitalTotal: this.formatInteger(digitalTotal),
      digitalShare: this.formatPercent(
        summary.sales_total > 0
          ? digitalTotal / summary.sales_total
          : null,
      ),
      digitalMetric: 'sales_digital_total',
      digitalChildren: [
        {
          label: 'Digital',
          value: this.formatInteger(summary.sales_digital),
          icon: 'ads_click',
          metric: 'sales_digital',
        },
        {
          label: 'Orgánica digital',
          value: this.formatInteger(summary.sales_digital_organic),
          icon: 'alternate_email',
          metric: 'sales_digital_organic',
        },
      ],
      webTotal: this.formatInteger(summary.sales_web),
      webShare: this.formatPercent(
        summary.sales_total > 0
          ? summary.sales_web / summary.sales_total
          : null,
      ),
      webMetric: 'sales_web',
      btlTotal: this.formatInteger(summary.sales_btl),
      btlShare: this.formatPercent(
        summary.sales_total > 0
          ? summary.sales_btl / summary.sales_total
          : null,
      ),
      btlMetric: 'sales_btl',
      btlOrigins,
    };
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

  openMetric(metric: string): void {
    this.openDetail(metric);
  }

  openOrigin(origin: FallbackOriginView): void {
    this.openDetail('origin', origin.key);
  }

  openBtlOrigin(origin: FallbackOriginView): void {
    this.openDetail('btl_origin', origin.key);
  }

  formatInteger(value: number): string {
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
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
  share: string;
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
        cutoffDate: this.cutoffDate,
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
}

import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges, inject } from '@angular/core';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { GraphChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import * as echarts from 'echarts/core';
import { EChartsCoreOption } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { NgxEchartsDirective, provideEchartsCore } from 'ngx-echarts';

import {
  MarketingSalesFunnelMetrics,
  MarketingSalesOriginBreakdown,
} from './marketing-sales-funnel.models';
import {
  MarketingSalesFunnelDetailDialogComponent,
} from './marketing-sales-funnel-detail-dialog.component';


echarts.use([
  GraphChart,
  TooltipComponent,
  CanvasRenderer,
]);

interface FlowNodeData {
  id: string;
  name: string;
  x: number;
  y: number;
  value: number;
  support: string;
  metric?: string;
  origin?: string;
  symbol: 'roundRect';
  symbolSize: [number, number];
  itemStyle: {
    color: string;
    borderColor: string;
    borderWidth: number;
    shadowBlur: number;
    shadowColor: string;
  };
  label: {
    show: boolean;
    position: 'inside';
    formatter: string;
    rich: Record<string, Record<string, unknown>>;
  };
}

interface FlowLinkData {
  source: string;
  target: string;
  lineStyle: {
    color: string;
    width: number;
    opacity: number;
    curveness: number;
  };
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
    NgxEchartsDirective,
  ],
  templateUrl: './marketing-sales-funnel-story.component.html',
  styleUrls: ['./marketing-sales-funnel-story.component.css'],
  providers: [provideEchartsCore({ echarts })],
})
export class MarketingSalesFunnelStoryComponent implements OnChanges {
  private readonly dialog = inject(MatDialog);

  @Input({ required: true }) month = '';
  @Input({ required: true }) summary: MarketingSalesFunnelMetrics | null | undefined = null;
  @Input() reconciliationLabel = '';

  chartOption: EChartsCoreOption = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['summary'] || changes['month']) {
      this.chartOption = this.buildChartOption();
    }
  }

  get narrative(): string {
    const summary = this.summary;
    if (!summary) {
      return '';
    }

    return `El funnel iVentas y la Venta Nueva convergen en ${this.formatInteger(summary.sales_iventas)} ventas trazables; las ${this.formatInteger(summary.sales_not_iventas)} restantes se explican por origen de venta.`;
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

  handleChartClick(event: { dataType?: string; data?: FlowNodeData }): void {
    if (event?.dataType !== 'node') {
      return;
    }

    const node = event.data;
    if (!node?.metric) {
      return;
    }

    this.openDetail(node.metric, node.origin);
  }

  openOrigin(origin: FallbackOriginView): void {
    this.openDetail('origin', origin.key);
  }

  private buildChartOption(): EChartsCoreOption {
    const summary = this.summary;
    if (!summary) {
      return {};
    }

    const orange = '#f0522d';
    const orangeSoft = '#fff8f4';
    const orangeLine = 'rgba(240, 82, 45, 0.62)';
    const gray = '#6b819d';
    const graySoft = '#f5f8fb';
    const grayLine = 'rgba(107, 129, 157, 0.58)';

    const nodes: FlowNodeData[] = [
      this.createFlowNode({
        id: 'leads',
        name: 'Leads iVentas',
        value: summary.leads_iventas,
        support: 'Creados en el mes + firstMessage',
        metric: 'leads_iventas',
        x: 130,
        y: 90,
        width: 190,
        height: 92,
        background: orangeSoft,
        border: orange,
      }),
      this.createFlowNode({
        id: 'visits',
        name: 'Visitas iVentas',
        value: summary.visits_iventas,
        support: 'Visitas que cruzan por teléfono',
        metric: 'visits_iventas',
        x: 410,
        y: 90,
        width: 180,
        height: 92,
        background: orangeSoft,
        border: orange,
      }),
      this.createFlowNode({
        id: 'sales-iventas',
        name: 'Ventas iVentas',
        value: summary.sales_iventas,
        support: `${this.formatPercent(summary.sales_total > 0 ? summary.sales_iventas / summary.sales_total : null)} de Venta Nueva · punto de unión`,
        metric: 'sales_iventas',
        x: 710,
        y: 205,
        width: 190,
        height: 108,
        background: '#fffdfb',
        border: orange,
        strong: true,
      }),
      this.createFlowNode({
        id: 'sales-total',
        name: 'Venta Nueva',
        value: summary.sales_total,
        support: '100% del universo de Venta Nueva',
        metric: 'sales_total',
        x: 130,
        y: 315,
        width: 190,
        height: 104,
        background: '#ffffff',
        border: orange,
        strong: true,
      }),
      this.createFlowNode({
        id: 'sales-no-match',
        name: 'Sin Match iVentas',
        value: summary.sales_not_iventas,
        support: `${this.formatPercent(summary.sales_total > 0 ? summary.sales_not_iventas / summary.sales_total : null)} de Venta Nueva · ver desglose abajo`,
        metric: 'sales_not_iventas',
        x: 420,
        y: 435,
        width: 200,
        height: 104,
        background: graySoft,
        border: gray,
      }),
      this.createFlowNode({
        id: 'publications',
        name: 'Venta por publicaciones',
        value: summary.sales_iventas_meta,
        support: `${this.formatPercent(summary.sales_total > 0 ? summary.sales_iventas_meta / summary.sales_total : null)} del total`,
        metric: 'sales_iventas_meta',
        x: 1035,
        y: 125,
        width: 205,
        height: 94,
        background: orangeSoft,
        border: orange,
      }),
      this.createFlowNode({
        id: 'organic',
        name: 'Orgánico',
        value: summary.sales_iventas_other,
        support: 'Entró a iVentas sin publicidad pagada',
        metric: 'origin',
        origin: 'IVENTAS_OTHER',
        x: 1035,
        y: 285,
        width: 205,
        height: 98,
        background: orangeSoft,
        border: orange,
      }),
    ];

    const links: FlowLinkData[] = [
      this.createFlowLink('leads', 'visits', summary.leads_iventas, orangeLine, 0),
      this.createFlowLink('visits', 'sales-iventas', summary.visits_iventas, orangeLine, 0.16),
      this.createFlowLink('sales-total', 'sales-iventas', summary.sales_iventas, orangeLine, -0.16),
      this.createFlowLink('sales-total', 'sales-no-match', summary.sales_not_iventas, grayLine, 0.18),
      this.createFlowLink('sales-iventas', 'publications', summary.sales_iventas_meta, orangeLine, -0.16),
      this.createFlowLink('sales-iventas', 'organic', summary.sales_iventas_other, orangeLine, 0.16),
    ];

    return {
      animationDuration: 450,
      tooltip: {
        trigger: 'item',
        backgroundColor: '#111827',
        borderWidth: 0,
        textStyle: {
          color: '#ffffff',
          fontSize: 12,
        },
        formatter: (params: any) => {
          if (params?.dataType !== 'node') {
            return '';
          }
          const data = params.data as FlowNodeData;
          return `<strong>${data.name}</strong><br>${this.formatInteger(data.value)}<br><span style="opacity:.72">${data.support}</span>`;
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'none',
          roam: false,
          left: 34,
          right: 34,
          top: 22,
          bottom: 22,
          data: nodes as any,
          links: links as any,
          symbol: 'roundRect',
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: [0, 10],
          lineStyle: {
            opacity: 0.65,
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: {
              opacity: 0.95,
            },
          },
          select: {
            disabled: true,
          },
          animationDurationUpdate: 350,
        },
      ],
    };
  }

  private createFlowNode(config: {
    id: string;
    name: string;
    value: number;
    support: string;
    metric?: string;
    origin?: string;
    x: number;
    y: number;
    width: number;
    height: number;
    background: string;
    border: string;
    strong?: boolean;
  }): FlowNodeData {
    const valueLabel = this.formatInteger(config.value);
    const actionLabel = config.metric ? 'Ver filas ↗' : '';

    return {
      id: config.id,
      name: config.name,
      x: config.x,
      y: config.y,
      value: config.value,
      support: config.support,
      metric: config.metric,
      origin: config.origin,
      symbol: 'roundRect',
      symbolSize: [config.width, config.height],
      itemStyle: {
        color: config.background,
        borderColor: config.border,
        borderWidth: config.strong ? 2 : 1.2,
        shadowBlur: config.strong ? 14 : 8,
        shadowColor: config.strong
          ? 'rgba(240, 82, 45, 0.12)'
          : 'rgba(15, 23, 42, 0.06)',
      },
      label: {
        show: true,
        position: 'inside',
        formatter: [
          `{title|${config.name}}`,
          `{value|${valueLabel}}`,
          `{support|${config.support}}`,
          actionLabel ? `{action|${actionLabel}}` : '',
        ].filter(Boolean).join('\n'),
        rich: {
          title: {
            color: '#20314a',
            fontSize: 13,
            fontWeight: 800,
            lineHeight: 20,
          },
          value: {
            color: '#13233d',
            fontSize: config.strong ? 27 : 24,
            fontWeight: 900,
            lineHeight: 33,
          },
          support: {
            color: '#64748b',
            fontSize: 9,
            fontWeight: 600,
            lineHeight: 15,
          },
          action: {
            color: '#f0522d',
            fontSize: 9,
            fontWeight: 800,
            lineHeight: 17,
          },
        },
      },
    };
  }

  private createFlowLink(
    source: string,
    target: string,
    value: number,
    color: string,
    curveness: number,
  ): FlowLinkData {
    return {
      source,
      target,
      lineStyle: {
        color,
        width: this.flowWidth(value),
        opacity: 0.72,
        curveness,
      },
    };
  }

  private flowWidth(value: number): number {
    if (value <= 0) {
      return 2;
    }
    return Math.max(3, Math.min(18, 3 + Math.sqrt(value) * 0.42));
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

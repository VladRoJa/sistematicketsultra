import { Injectable } from '@angular/core';
import {
  Row,
  Workbook,
  Worksheet,
} from 'exceljs';

import {
  MarketingAttributionDetailResponse,
  MarketingAttributionDetailRow,
  MarketingDashboardResponse,
  MarketingDataQuality,
  MarketingMetrics,
  MarketingScope,
} from './marketing.models';

interface SummaryMetric {
  label: string;
  value: number | null;
  definition: string;
  format: 'currency' | 'integer' | 'percent';
}

@Injectable({
  providedIn: 'root',
})
export class MarketingExcelExportService {
  private readonly orange = 'E54525';
  private readonly charcoal = '202329';
  private readonly gray50 = 'F8FAFC';
  private readonly gray100 = 'F1F5F9';
  private readonly gray200 = 'E2E8F0';
  private readonly gray500 = '64748B';
  private readonly white = 'FFFFFF';
  private readonly danger = '991B1B';
  private readonly dangerSoft = 'FEF2F2';

  async exportDashboard(
    dashboard: MarketingDashboardResponse,
  ): Promise<void> {
    const workbook = this.createWorkbook();

    this.buildDashboardSummarySheet(
      workbook,
      dashboard,
    );
    this.buildBranchSheet(
      workbook,
      dashboard,
    );
    this.buildQualitySheet(
      workbook,
      dashboard.data_quality,
      dashboard.month,
      dashboard.scope,
    );

    await this.downloadWorkbook(
      workbook,
      `marketing_global_${dashboard.month}.xlsx`,
    );
  }

  async exportAttributionCohort(
    detail: MarketingAttributionDetailResponse,
  ): Promise<void> {
    const workbook = this.createWorkbook();

    this.buildCohortSummarySheet(
      workbook,
      detail,
    );
    this.buildCohortDetailSheet(
      workbook,
      detail,
    );

    const scopeName = this.resolveCohortScopeName(
      detail,
    );

    await this.downloadWorkbook(
      workbook,
      [
        'marketing_cohorte',
        detail.month,
        this.slugify(scopeName),
      ].join('_') + '.xlsx',
    );
  }

  private createWorkbook(): Workbook {
    const workbook = new Workbook();

    workbook.creator = 'Suite Ultra';
    workbook.company = 'UltraGym';
    workbook.subject = 'Marketing y Conversión';
    workbook.created = new Date();
    workbook.modified = new Date();

    return workbook;
  }

  private buildDashboardSummarySheet(
    workbook: Workbook,
    dashboard: MarketingDashboardResponse,
  ): void {
    const sheet = workbook.addWorksheet(
      'Resumen',
      {
        views: [
          {
            state: 'frozen',
            ySplit: 7,
          },
        ],
      },
    );

    this.addReportTitle(
      sheet,
      'Marketing y Conversión',
      'Resumen global del mes',
      3,
    );

    sheet.getCell('A4').value = 'Mes';
    sheet.getCell('B4').value = dashboard.month;

    sheet.getCell('A5').value = 'Alcance';
    sheet.getCell('B5').value = this.resolveScopeLabel(
      dashboard.scope,
    );

    sheet.getCell('A6').value = 'Estado de cohorte';
    sheet.getCell('B6').value = (
      dashboard.data_quality.cohort_complete
        ? 'Completa'
        : 'En curso'
    );

    this.styleMetadataRange(
      sheet,
      'A4:B6',
    );

    const headerRow = sheet.getRow(8);
    headerRow.values = [
      'Métrica',
      'Valor',
      'Definición',
    ];
    this.styleHeaderRow(headerRow);

    const metrics = this.buildSummaryMetrics(
      dashboard.summary,
    );

    metrics.forEach((metric, index) => {
      const rowNumber = index + 9;
      const row = sheet.getRow(rowNumber);

      row.values = [
        metric.label,
        metric.value,
        metric.definition,
      ];

      this.applyMetricFormat(
        row.getCell(2),
        metric.format,
      );
    });

    sheet.autoFilter = {
      from: 'A8',
      to: `C${metrics.length + 8}`,
    };

    sheet.getColumn(1).width = 27;
    sheet.getColumn(2).width = 18;
    sheet.getColumn(3).width = 42;

    sheet.getColumn(3).alignment = {
      wrapText: true,
      vertical: 'middle',
    };

    this.applyBodyBorders(
      sheet,
      9,
      metrics.length + 8,
      1,
      3,
    );
  }

  private buildBranchSheet(
    workbook: Workbook,
    dashboard: MarketingDashboardResponse,
  ): void {
    const sheet = workbook.addWorksheet(
      'Sucursales',
      {
        views: [
          {
            state: 'frozen',
            ySplit: 1,
            xSplit: 1,
          },
        ],
      },
    );

    const headers = [
      'Sucursal',
      'Inversión',
      'Leads',
      'Visitantes',
      'Ventas atribuidas',
      'Ingreso atribuido',
      'Costo por lead',
      'Costo por visita',
      'Costo por venta',
      'Lead → visita',
      'Visita → venta',
      'Lead → venta',
    ];

    const headerRow = sheet.getRow(1);
    headerRow.values = headers;
    this.styleHeaderRow(headerRow);

    dashboard.branches.forEach(
      (branch, index) => {
        const row = sheet.getRow(index + 2);

        row.values = [
          branch.sucursal,
          branch.investment,
          branch.leads,
          branch.visits,
          branch.sales,
          branch.sales_revenue,
          branch.cost_per_lead,
          branch.cost_per_visit,
          branch.cost_per_sale,
          branch.lead_to_visit_rate,
          branch.visit_to_sale_rate,
          branch.lead_to_sale_rate,
        ];
      },
    );

    const lastRow = dashboard.branches.length + 1;

    sheet.autoFilter = {
      from: 'A1',
      to: `L${lastRow}`,
    };

    this.applyColumnFormat(
      sheet,
      [2, 6, 7, 8, 9],
      '$#,##0.00;[Red]-$#,##0.00',
    );
    this.applyColumnFormat(
      sheet,
      [3, 4, 5],
      '#,##0',
    );
    this.applyColumnFormat(
      sheet,
      [10, 11, 12],
      '0.0%',
    );

    sheet.getColumn(1).width = 28;
    sheet.getColumn(2).width = 15;
    sheet.getColumn(3).width = 12;
    sheet.getColumn(4).width = 13;
    sheet.getColumn(5).width = 18;
    sheet.getColumn(6).width = 19;
    sheet.getColumn(7).width = 17;
    sheet.getColumn(8).width = 18;
    sheet.getColumn(9).width = 17;
    sheet.getColumn(10).width = 16;
    sheet.getColumn(11).width = 16;
    sheet.getColumn(12).width = 15;

    this.applyBodyBorders(
      sheet,
      2,
      lastRow,
      1,
      12,
    );

    for (
      let rowNumber = 2;
      rowNumber <= lastRow;
      rowNumber += 1
    ) {
      if (rowNumber % 2 === 0) {
        this.applyAlternateFill(
          sheet.getRow(rowNumber),
        );
      }
    }
  }

  private buildQualitySheet(
    workbook: Workbook,
    quality: MarketingDataQuality,
    month: string,
    scope: MarketingScope,
  ): void {
    const sheet = workbook.addWorksheet(
      'Calidad de datos',
    );

    this.addReportTitle(
      sheet,
      'Calidad de datos',
      `Marketing ${month}`,
      3,
    );

    sheet.getCell('A4').value = 'Alcance';
    sheet.getCell('B4').value =
      this.resolveScopeLabel(scope);

    const headerRow = sheet.getRow(6);
    headerRow.values = [
      'Indicador',
      'Valor',
      'Interpretación',
    ];
    this.styleHeaderRow(headerRow);

    const rows: Array<
      [string, string | number | null, string]
    > = [
      [
        'Modo de leads',
        quality.lead_mode,
        'Origen utilizado para contabilizar leads.',
      ],
      [
        'Modo de atribución',
        quality.sales_attribution_mode,
        'Regla utilizada para conciliar visita y venta.',
      ],
      [
        'Cohorte completa',
        quality.cohort_complete ? 'Sí' : 'No',
        'Indica si terminó la ventana de 30 días.',
      ],
      [
        'Eventos de visita elegibles',
        quality.eligible_visit_events,
        'Eventos que cumplen las reglas de visita.',
      ],
      [
        'Visitantes únicos',
        quality.unique_visitors,
        'Teléfonos únicos por sucursal.',
      ],
      [
        'Eventos con teléfono válido',
        quality.visit_events_with_valid_phone,
        'Eventos disponibles para conciliación.',
      ],
      [
        'Eventos sin teléfono válido',
        quality.visit_events_without_valid_phone,
        'Eventos que no pueden atribuirse.',
      ],
      [
        'Cobertura de teléfono',
        quality.visit_phone_coverage_rate,
        'Porcentaje de eventos con teléfono válido.',
      ],
    ];

    rows.forEach((values, index) => {
      sheet.getRow(index + 7).values = values;
    });

    sheet.getCell('B14').numFmt = '0.0%';

    const limitationsStart = rows.length + 9;

    sheet.getCell(
      `A${limitationsStart}`,
    ).value = 'Limitaciones informadas';
    sheet.getCell(
      `A${limitationsStart}`,
    ).font = {
      bold: true,
      color: {
        argb: this.charcoal,
      },
    };

    const limitations = (
      quality.limitations.length > 0
        ? quality.limitations
        : ['Sin limitaciones adicionales.']
    );

    limitations.forEach(
      (limitation, index) => {
        const rowNumber =
          limitationsStart + index + 1;

        sheet.mergeCells(
          rowNumber,
          1,
          rowNumber,
          3,
        );

        const cell = sheet.getCell(
          rowNumber,
          1,
        );

        cell.value = (
          quality.limitations.length > 0
            ? `• ${limitation}`
            : limitation
        );
        cell.alignment = {
          vertical: 'middle',
          wrapText: true,
        };
      },
    );

    sheet.getColumn(1).width = 30;
    sheet.getColumn(2).width = 25;
    sheet.getColumn(3).width = 46;

    sheet.getColumn(3).alignment = {
      wrapText: true,
      vertical: 'middle',
    };

    this.applyBodyBorders(
      sheet,
      7,
      rows.length + 6,
      1,
      3,
    );
  }

  private buildCohortSummarySheet(
    workbook: Workbook,
    detail: MarketingAttributionDetailResponse,
  ): void {
    const sheet = workbook.addWorksheet(
      'Resumen cohorte',
    );

    this.addReportTitle(
      sheet,
      'Ventas atribuidas',
      'Resumen de cohorte',
      3,
    );

    const scopeName = this.resolveCohortScopeName(
      detail,
    );

    const rows: Array<
      [string, string | number]
    > = [
      ['Mes de visitas', detail.month],
      ['Alcance', scopeName],
      [
        'Ventas atribuidas',
        detail.summary.sales,
      ],
      [
        'Ingreso atribuido',
        detail.summary.sales_revenue,
      ],
      [
        'Casos por revisar',
        detail.summary.review_sales,
      ],
      [
        'Integrantes adicionales de plan familiar',
        detail.summary.family_plan_additional_members,
      ],
      [
        'Snapshot de visitas',
        detail.source.visit_snapshot_id ?? '—',
      ],
      [
        'Snapshots de ventas',
        detail.source.sales_snapshot_ids.join(', '),
      ],
      [
        'Regla de atribución',
        'Teléfono exacto, misma sucursal y ventana de hasta 30 días',
      ],
    ];

    rows.forEach((values, index) => {
      const row = sheet.getRow(index + 4);

      row.values = values;
      row.getCell(1).font = {
        bold: true,
        color: {
          argb: this.gray500,
        },
      };
    });

    sheet.getCell('B6').numFmt = '#,##0';
    sheet.getCell('B7').numFmt =
      '$#,##0.00;[Red]-$#,##0.00';
    sheet.getCell('B8').numFmt = '#,##0';
    sheet.getCell('B9').numFmt = '#,##0';

    sheet.getColumn(1).width = 36;
    sheet.getColumn(2).width = 52;
    sheet.getColumn(2).alignment = {
      wrapText: true,
      vertical: 'middle',
    };

    this.applyBodyBorders(
      sheet,
      4,
      rows.length + 3,
      1,
      2,
    );
  }

  private buildCohortDetailSheet(
    workbook: Workbook,
    detail: MarketingAttributionDetailResponse,
  ): void {
    const sheet = workbook.addWorksheet(
      'Detalle cohorte',
      {
        views: [
          {
            state: 'frozen',
            ySplit: 1,
            xSplit: (
              detail.filters.sucursal_id === null
                ? 1
                : 0
            ),
          },
        ],
      },
    );

    const branchScoped =
      detail.filters.sucursal_id !== null;

    const headers = [
      ...(branchScoped ? [] : ['Sucursal']),
      'ID socio',
      'Socio',
      'Teléfono',
      'Fecha visita',
      'Fecha pago',
      'Días a venta',
      'Tipo de visita',
      'Tipo de membresía',
      'Tarifa',
      'Inscripción',
      'Pase',
      'Lugar de pago',
      'Folio',
      'Total listado',
      'Total pagado',
      'Clasificación',
      'Snapshot ID',
      'Fila fuente',
    ];

    const headerRow = sheet.getRow(1);
    headerRow.values = headers;
    this.styleHeaderRow(headerRow);

    detail.rows.forEach((row, index) => {
      const excelRow = sheet.getRow(index + 2);

      excelRow.values = this.mapCohortRow(
        row,
        branchScoped,
      );

      if (row.venta_sin_ingreso_positivo) {
        excelRow.eachCell((cell) => {
          cell.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: {
              argb: this.dangerSoft,
            },
          };
        });

        const paidColumn = branchScoped ? 15 : 16;
        const reviewColumn = branchScoped ? 16 : 17;

        excelRow.getCell(paidColumn).font = {
          bold: true,
          color: {
            argb: this.danger,
          },
        };

        excelRow.getCell(reviewColumn).font = {
          bold: true,
          color: {
            argb: this.danger,
          },
        };
      }
    });

    const lastRow = detail.rows.length + 1;
    const lastColumn = headers.length;

    sheet.autoFilter = {
      from: {
        row: 1,
        column: 1,
      },
      to: {
        row: lastRow,
        column: lastColumn,
      },
    };

    const dateStart = branchScoped ? 4 : 5;
    const dateEnd = dateStart + 1;
    const amountStart = branchScoped ? 14 : 15;
    const amountEnd = amountStart + 1;

    this.applyColumnFormat(
      sheet,
      [dateStart, dateEnd],
      'dd/mm/yyyy',
    );

    this.applyColumnFormat(
      sheet,
      [amountStart, amountEnd],
      '$#,##0.00;[Red]-$#,##0.00',
    );

    this.setCohortColumnWidths(
      sheet,
      branchScoped,
    );

    this.applyBodyBorders(
      sheet,
      2,
      lastRow,
      1,
      lastColumn,
    );

    for (
      let rowNumber = 2;
      rowNumber <= lastRow;
      rowNumber += 1
    ) {
      const sourceRow =
        detail.rows[rowNumber - 2];

      if (
        rowNumber % 2 === 0 &&
        !sourceRow.venta_sin_ingreso_positivo
      ) {
        this.applyAlternateFill(
          sheet.getRow(rowNumber),
        );
      }
    }
  }

  private mapCohortRow(
    row: MarketingAttributionDetailRow,
    branchScoped: boolean,
  ): Array<string | number | Date | null> {
    return [
      ...(branchScoped ? [] : [row.sucursal]),
      row.id_socio,
      row.socio,
      row.telefono,
      this.parseIsoDate(row.fecha_visita),
      this.parseIsoDate(row.fecha_pago),
      row.dias_a_venta,
      row.tipo_visita,
      row.tipo_membresia,
      row.tarifa,
      row.inscripcion,
      row.pase,
      row.lugar_pago,
      row.id_folio,
      row.total,
      row.total_pagado,
      this.resolveAttributionClassification(
        row,
      ),
      row.snapshot_id,
      row.source_row_id,
    ];
  }

  private resolveAttributionClassification(
    row: MarketingAttributionDetailRow,
  ): string {
    if (
      row.attribution_classification
      === 'FAMILY_PLAN_ADDITIONAL_MEMBER'
    ) {
      return (
        'Integrante adicional de plan familiar '
        + '· importe en titular'
      );
    }

    if (
      row.attribution_classification
      === 'NON_POSITIVE_AMOUNT_REVIEW'
    ) {
      return 'Revisar importe en fuente';
    }

    return 'Venta estándar';
  }

  private buildSummaryMetrics(
    metrics: MarketingMetrics,
  ): SummaryMetric[] {
    return [
      {
        label: 'Inversión',
        value: metrics.investment,
        definition: 'Captura manual del mes.',
        format: 'currency',
      },
      {
        label: 'Leads',
        value: metrics.leads,
        definition: (
          'Contactos del canónico iVentas con firstMessageAt '
          + 'y al menos un tag META_AD.'
        ),
        format: 'integer',
      },
      {
        label: 'Visitantes',
        value: metrics.visits,
        definition: 'Teléfonos únicos elegibles.',
        format: 'integer',
      },
      {
        label: 'Ventas atribuidas',
        value: metrics.sales,
        definition:
          'Ventas conciliadas por teléfono y misma sucursal.',
        format: 'integer',
      },
      {
        label: 'Ingreso atribuido',
        value: metrics.sales_revenue,
        definition: (
          'Total pagado de las ventas conciliadas.'
        ),
        format: 'currency',
      },
      {
        label: 'Costo por lead',
        value: metrics.cost_per_lead,
        definition: 'Inversión dividida entre leads.',
        format: 'currency',
      },
      {
        label: 'Costo por visita',
        value: metrics.cost_per_visit,
        definition: (
          'Inversión dividida entre visitantes.'
        ),
        format: 'currency',
      },
      {
        label: 'Costo por venta',
        value: metrics.cost_per_sale,
        definition: (
          'Inversión dividida entre ventas atribuidas.'
        ),
        format: 'currency',
      },
      {
        label: 'Lead → visita',
        value: metrics.lead_to_visit_rate,
        definition: 'Visitantes divididos entre leads.',
        format: 'percent',
      },
      {
        label: 'Visita → venta',
        value: metrics.visit_to_sale_rate,
        definition: (
          'Ventas atribuidas divididas entre visitantes.'
        ),
        format: 'percent',
      },
      {
        label: 'Lead → venta',
        value: metrics.lead_to_sale_rate,
        definition: (
          'Ventas atribuidas divididas entre leads.'
        ),
        format: 'percent',
      },
    ];
  }

  private addReportTitle(
    sheet: Worksheet,
    title: string,
    subtitle: string,
    columns: number,
  ): void {
    sheet.mergeCells(
      1,
      1,
      1,
      columns,
    );
    sheet.mergeCells(
      2,
      1,
      2,
      columns,
    );

    const titleCell = sheet.getCell(1, 1);
    titleCell.value = title;
    titleCell.font = {
      bold: true,
      size: 20,
      color: {
        argb: this.charcoal,
      },
    };

    const subtitleCell = sheet.getCell(2, 1);
    subtitleCell.value = subtitle;
    subtitleCell.font = {
      bold: true,
      size: 11,
      color: {
        argb: this.orange,
      },
    };

    sheet.getRow(1).height = 30;
    sheet.getRow(2).height = 22;
  }

  private styleHeaderRow(row: Row): void {
    row.height = 24;

    row.eachCell((cell) => {
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: {
          argb: this.charcoal,
        },
      };
      cell.font = {
        bold: true,
        color: {
          argb: this.white,
        },
        size: 10,
      };
      cell.alignment = {
        vertical: 'middle',
        horizontal: 'center',
        wrapText: true,
      };
      cell.border = this.buildBorder();
    });
  }

  private styleMetadataRange(
    sheet: Worksheet,
    _range: string,
  ): void {
    for (
      let rowNumber = 4;
      rowNumber <= 6;
      rowNumber += 1
    ) {
      for (
        let columnNumber = 1;
        columnNumber <= 2;
        columnNumber += 1
      ) {
        const cell = sheet.getCell(
          rowNumber,
          columnNumber,
        );

        cell.border = this.buildBorder();
        cell.alignment = {
          vertical: 'middle',
          wrapText: true,
        };
      }

      sheet.getCell(rowNumber, 1).font = {
        bold: true,
        color: {
          argb: this.gray500,
        },
      };
    }
  }

  private applyMetricFormat(
    cell: {
      numFmt: string;
    },
    format: SummaryMetric['format'],
  ): void {
    if (format === 'currency') {
      cell.numFmt =
        '$#,##0.00;[Red]-$#,##0.00';
      return;
    }

    if (format === 'percent') {
      cell.numFmt = '0.0%';
      return;
    }

    cell.numFmt = '#,##0';
  }

  private applyColumnFormat(
    sheet: Worksheet,
    columns: number[],
    numberFormat: string,
  ): void {
    columns.forEach((columnNumber) => {
      sheet.getColumn(columnNumber).numFmt =
        numberFormat;
    });
  }

  private applyBodyBorders(
    sheet: Worksheet,
    firstRow: number,
    lastRow: number,
    firstColumn: number,
    lastColumn: number,
  ): void {
    if (lastRow < firstRow) {
      return;
    }

    for (
      let rowNumber = firstRow;
      rowNumber <= lastRow;
      rowNumber += 1
    ) {
      for (
        let columnNumber = firstColumn;
        columnNumber <= lastColumn;
        columnNumber += 1
      ) {
        const cell = sheet.getCell(
          rowNumber,
          columnNumber,
        );

        cell.border = this.buildBorder();
        cell.alignment = {
          vertical: 'middle',
          wrapText: true,
        };
      }
    }
  }

  private applyAlternateFill(row: Row): void {
    row.eachCell((cell) => {
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: {
          argb: this.gray50,
        },
      };
    });
  }

  private buildBorder() {
    return {
      top: {
        style: 'thin' as const,
        color: {
          argb: this.gray200,
        },
      },
      left: {
        style: 'thin' as const,
        color: {
          argb: this.gray200,
        },
      },
      bottom: {
        style: 'thin' as const,
        color: {
          argb: this.gray200,
        },
      },
      right: {
        style: 'thin' as const,
        color: {
          argb: this.gray200,
        },
      },
    };
  }

  private setCohortColumnWidths(
    sheet: Worksheet,
    branchScoped: boolean,
  ): void {
    const widths = branchScoped
      ? [
          15,
          29,
          16,
          14,
          14,
          12,
          24,
          20,
          32,
          22,
          29,
          18,
          22,
          16,
          16,
          13,
          13,
          13,
        ]
      : [
          25,
          15,
          29,
          16,
          14,
          14,
          12,
          24,
          20,
          32,
          22,
          29,
          18,
          22,
          16,
          16,
          13,
          13,
          13,
        ];

    widths.forEach((width, index) => {
      sheet.getColumn(index + 1).width = width;
    });
  }

  private resolveScopeLabel(
    scope: MarketingScope,
  ): string {
    const branchCount = scope.branch_ids.length;

    if (scope.type === 'GLOBAL') {
      return `Global · ${branchCount} sucursales`;
    }

    if (scope.type === 'REGIONAL') {
      return `Regional · ${branchCount} sucursales`;
    }

    if (scope.type === 'BRANCH') {
      return `Sucursal · ${branchCount} sucursal`;
    }

    return `${scope.type} · ${branchCount} sucursales`;
  }

  private resolveCohortScopeName(
    detail: MarketingAttributionDetailResponse,
  ): string {
    if (detail.filters.sucursal_id === null) {
      return 'Global';
    }

    return (
      detail.rows[0]?.sucursal ||
      `Sucursal ${detail.filters.sucursal_id}`
    );
  }

  private parseIsoDate(value: string): Date {
    return new Date(`${value}T12:00:00`);
  }

  private slugify(value: string): string {
    return value
      .trim()
      .toLocaleLowerCase('es-MX')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 60);
  }

  private async downloadWorkbook(
    workbook: Workbook,
    fileName: string,
  ): Promise<void> {
    const buffer = await workbook.xlsx.writeBuffer();

    const blob = new Blob(
      [buffer as BlobPart],
      {
        type: (
          'application/vnd.openxmlformats-'
          + 'officedocument.spreadsheetml.sheet'
        ),
      },
    );

    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');

    anchor.href = url;
    anchor.download = fileName;
    anchor.style.display = 'none';

    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    window.setTimeout(
      () => URL.revokeObjectURL(url),
      1000,
    );
  }
}

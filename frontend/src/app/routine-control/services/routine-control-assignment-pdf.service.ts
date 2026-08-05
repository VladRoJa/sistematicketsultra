import { Injectable } from '@angular/core';

import type {
  jsPDF as JsPdfDocument,
} from 'jspdf';


type PdfColor = [
  number,
  number,
  number,
];


export interface RoutineControlAssignmentPdfRow {
  regionName: string;
  branchName: string;
  conRutina: number;
  percentConRutina: number;
  sinRutina: number;
  percentSinRutina: number;
  noRequiereRutina: number;
  total: number;
}


export interface RoutineControlAssignmentPdfTotals {
  conRutina: number;
  percentConRutina: number;
  sinRutina: number;
  percentSinRutina: number;
  noRequiereRutina: number;
  total: number;
}


export interface RoutineControlAssignmentPdfData {
  monthFromValue: string;
  monthToValue: string;
  periodLabel: string;
  rows: RoutineControlAssignmentPdfRow[];
  totals: RoutineControlAssignmentPdfTotals;
}


@Injectable({
  providedIn: 'root',
})
export class RoutineControlAssignmentPdfService {
  private static readonly BUSINESS_TIME_ZONE =
    'America/Tijuana';

  async exportReport(
    data: RoutineControlAssignmentPdfData,
  ): Promise<void> {
    const [
      { jsPDF },
      { autoTable },
    ] = await Promise.all([
      import('jspdf'),
      import('jspdf-autotable'),
    ]);

    const document = new jsPDF({
      orientation: 'landscape',
      unit: 'mm',
      format: 'a4',
      compress: true,
    });

    const periodLabel =
      this.pdfText(data.periodLabel);

    const logoDataUrl =
      await this.loadImageDataUrl(
        '/assets/branding/ultra-gym-logo.png',
      );

    const denseReport =
      data.rows.length > 18;

    const pageWidth =
      document.internal.pageSize.getWidth();

    const denseTableWidth = 258;

    const horizontalMargin =
      denseReport
        ? Math.max(
            6,
            (
              pageWidth
              - denseTableWidth
            ) / 2,
          )
        : 8;

    const regionColorByName =
      this.regionColorMap(data.rows);

    const body = data.rows.map(
      (row) => [
        this.pdfText(row.regionName),
        this.pdfText(row.branchName),
        this.integer(row.conRutina),
        this.percentage(row.percentConRutina),
        this.integer(row.sinRutina),
        this.percentage(row.percentSinRutina),
        this.integer(row.noRequiereRutina),
        this.integer(row.total),
      ],
    );

    if (!body.length) {
      body.push([
        'Sin datos para el periodo',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
      ]);
    }

    autoTable(document, {
      head: [[
        'Región',
        'Sucursal',
        'Con rutina',
        '%',
        'Sin rutina',
        '%',
        'No requiere rutina de Ultra',
        'Total',
      ]],
      body,
      foot: [[
        {
          content: 'Total general',
          colSpan: 2,
          styles: {
            halign: 'center',
          },
        },
        this.integer(data.totals.conRutina),
        this.percentage(
          data.totals.percentConRutina,
        ),
        this.integer(data.totals.sinRutina),
        this.percentage(
          data.totals.percentSinRutina,
        ),
        this.integer(
          data.totals.noRequiereRutina,
        ),
        this.integer(data.totals.total),
      ]],
      theme: 'grid',
      startY: 22,
      tableWidth:
        denseReport
          ? denseTableWidth
          : 'auto',
      margin: {
        top: 22,
        right: horizontalMargin,
        bottom: 17,
        left: horizontalMargin,
      },
      showHead: 'everyPage',
      showFoot: 'lastPage',
      pageBreak: 'avoid',
      rowPageBreak: 'avoid',
      styles: {
        font: 'helvetica',
        fontSize:
          denseReport ? 6.3 : 7.2,
        cellPadding:
          denseReport ? 0.65 : 1.7,
        valign: 'middle',
        overflow: 'linebreak',
        lineColor: [226, 232, 240],
        lineWidth: 0.1,
        textColor: [51, 65, 85],
        minCellHeight:
          denseReport ? 5.1 : 6.5,
      },
      headStyles: {
        fillColor: [7, 31, 86],
        textColor: [255, 255, 255],
        fontStyle: 'bold',
        fontSize:
          denseReport ? 6 : 6.8,
        halign: 'center',
        minCellHeight:
          denseReport ? 5.6 : 7,
      },
      bodyStyles: {
        fillColor: [255, 255, 255],
      },
      alternateRowStyles: {
        fillColor: [248, 250, 252],
      },
      footStyles: {
        fillColor: [7, 31, 86],
        textColor: [255, 255, 255],
        fontStyle: 'bold',
        halign: 'center',
        valign: 'middle',
      },
      columnStyles: {
        0: {
          cellWidth:
            denseReport ? 64 : 51,
        },
        1: {
          cellWidth:
            denseReport ? 50 : 45,
          fontStyle: 'bold',
        },
        2: {
          cellWidth:
            denseReport ? 22 : 24,
          halign: 'center',
        },
        3: {
          cellWidth:
            denseReport ? 17 : 19,
          halign: 'center',
        },
        4: {
          cellWidth:
            denseReport ? 22 : 24,
          halign: 'center',
        },
        5: {
          cellWidth:
            denseReport ? 17 : 19,
          halign: 'center',
        },
        6: {
          cellWidth:
            denseReport ? 48 : 52,
          halign: 'center',
        },
        7: {
          cellWidth:
            denseReport ? 18 : 20,
          halign: 'center',
          fontStyle: 'bold',
        },
      },
      didParseCell: (hookData) => {
        if (hookData.section !== 'body') {
          return;
        }

        if (hookData.column.index === 0) {
          const regionName = String(
            hookData.cell.raw || '',
          );

          hookData.cell.styles.fillColor =
            regionColorByName.get(regionName)
            || [229, 69, 37];

          hookData.cell.styles.textColor =
            [255, 255, 255];

          hookData.cell.styles.fontStyle =
            'bold';

          hookData.cell.styles.fontSize =
            denseReport ? 5.7 : 6.3;
        }

        if (
          hookData.column.index === 3
          || hookData.column.index === 5
        ) {
          const value = Number(
            String(hookData.cell.raw)
              .replace('%', ''),
          );

          const isConRutina =
            hookData.column.index === 3;

          hookData.cell.styles.fillColor =
            this.percentageFillColor(
              value,
              isConRutina,
            );

          hookData.cell.styles.textColor =
            this.percentageTextColor(
              value,
              isConRutina,
            );

          hookData.cell.styles.fontStyle =
            'bold';
        }

        if (hookData.column.index === 6) {
          hookData.cell.styles.fillColor =
            [248, 250, 252];
          hookData.cell.styles.textColor =
            [100, 116, 139];
          hookData.cell.styles.fontStyle =
            'bold';
        }
      },
      didDrawPage: () => {
        this.drawHeader(
          document,
          periodLabel,
        );
      },
    });

    this.drawPageFooters(
      document,
      logoDataUrl,
    );

    document.setProperties({
      title:
        `Reporte de asignación de rutinas - `
        + periodLabel,
      subject:
        'Control de Rutinas',
      author:
        'Suite Ultra',
      creator:
        'Suite Ultra',
    });

    document.save(
      this.filename(
        data.monthFromValue,
        data.monthToValue,
      ),
    );
  }

  private drawHeader(
    document: JsPdfDocument,
    periodLabel: string,
  ): void {
    const pageWidth =
      document.internal.pageSize.getWidth();

    document.setFillColor(7, 31, 86);
    document.rect(
      0,
      0,
      pageWidth,
      18,
      'F',
    );

    document.setFillColor(229, 69, 37);
    document.rect(
      0,
      0,
      6,
      18,
      'F',
    );

    document.setFont(
      'helvetica',
      'bold',
    );
    document.setFontSize(12);
    document.setTextColor(
      255,
      255,
      255,
    );

    document.text(
      'Reporte de asignación de rutinas',
      12,
      7.5,
    );

    document.setFontSize(6.5);
    document.setFont(
      'helvetica',
      'normal',
    );
    document.setTextColor(
      226,
      232,
      240,
    );

    document.text(
      `Periodo de venta: ${periodLabel}`,
      12,
      13.5,
    );

    document.setFont(
      'helvetica',
      'bold',
    );
    document.setTextColor(
      255,
      255,
      255,
    );

    document.text(
      'SUITE ULTRA',
      pageWidth - 10,
      7.5,
      {
        align: 'right',
      },
    );

    document.setFont(
      'helvetica',
      'normal',
    );
    document.setFontSize(5.5);
    document.setTextColor(
      203,
      213,
      225,
    );

    document.text(
      'Control de Rutinas',
      pageWidth - 10,
      13.5,
      {
        align: 'right',
      },
    );
  }

  private drawPageFooters(
    document: JsPdfDocument,
    logoDataUrl: string,
  ): void {
    const pageCount =
      document.getNumberOfPages();

    const pageWidth =
      document.internal.pageSize.getWidth();

    const pageHeight =
      document.internal.pageSize.getHeight();

    const generatedAt =
      new Intl.DateTimeFormat(
        'es-MX',
        {
          timeZone:
            RoutineControlAssignmentPdfService
              .BUSINESS_TIME_ZONE,
          dateStyle: 'medium',
          timeStyle: 'short',
        },
      ).format(new Date());

    for (
      let page = 1;
      page <= pageCount;
      page += 1
    ) {
      document.setPage(page);

      document.setDrawColor(
        226,
        232,
        240,
      );

      document.line(
        6,
        pageHeight - 13,
        pageWidth - 6,
        pageHeight - 13,
      );

      document.setFont(
        'helvetica',
        'normal',
      );
      document.setFontSize(5.5);
      document.setTextColor(
        100,
        116,
        139,
      );

      document.text(
        `Generado: ${generatedAt}`,
        6,
        pageHeight - 4,
      );

      document.text(
        `Página ${page} de ${pageCount}`,
        pageWidth / 2,
        pageHeight - 4,
        {
          align: 'center',
        },
      );

      const logoWidth = 11.5;
      const logoHeight = 10.6;

      document.addImage(
        logoDataUrl,
        'PNG',
        pageWidth - 6 - logoWidth,
        pageHeight - 11.5,
        logoWidth,
        logoHeight,
        'ultra-gym-logo',
        'FAST',
      );
    }
  }

  private async loadImageDataUrl(
    imageUrl: string,
  ): Promise<string> {
    const response = await fetch(imageUrl);

    if (!response.ok) {
      throw new Error(
        `No se pudo cargar el logo del PDF: `
        + `${response.status}`,
      );
    }

    const imageBlob = await response.blob();

    return new Promise<string>(
      (resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => {
          if (typeof reader.result === 'string') {
            resolve(reader.result);
            return;
          }

          reject(
            new Error(
              'El logo del PDF no pudo '
              + 'convertirse a imagen.',
            ),
          );
        };

        reader.onerror = () => {
          reject(
            new Error(
              'No se pudo leer el logo del PDF.',
            ),
          );
        };

        reader.readAsDataURL(imageBlob);
      },
    );
  }

  private regionColorMap(
    rows: RoutineControlAssignmentPdfRow[],
  ): Map<string, PdfColor> {
    const palette: PdfColor[] = [
      [159, 47, 47],
      [8, 169, 213],
      [64, 53, 82],
      [242, 125, 22],
      [22, 101, 52],
      [37, 99, 235],
    ];

    const regionNames = Array.from(
      new Set(
        rows.map(
          (row) => row.regionName,
        ),
      ),
    ).sort(
      (left, right) =>
        left.localeCompare(
          right,
          'es',
          {
            sensitivity: 'base',
          },
        ),
    );

    return new Map(
      regionNames.map(
        (regionName, index) => [
          regionName,
          palette[index % palette.length],
        ],
      ),
    );
  }

  private percentageFillColor(
    value: number,
    isConRutina: boolean,
  ): PdfColor {
    if (isConRutina) {
      if (value >= 70) {
        return [187, 247, 208];
      }

      if (value >= 40) {
        return [254, 240, 138];
      }

      if (value > 0) {
        return [254, 215, 170];
      }

      return [254, 202, 202];
    }

    if (value <= 30) {
      return [187, 247, 208];
    }

    if (value <= 60) {
      return [254, 240, 138];
    }

    if (value < 100) {
      return [254, 215, 170];
    }

    return [254, 202, 202];
  }

  private percentageTextColor(
    value: number,
    isConRutina: boolean,
  ): PdfColor {
    if (isConRutina) {
      if (value >= 70) {
        return [22, 101, 52];
      }

      if (value >= 40) {
        return [133, 77, 14];
      }

      if (value > 0) {
        return [154, 52, 18];
      }

      return [153, 27, 27];
    }

    if (value <= 30) {
      return [22, 101, 52];
    }

    if (value <= 60) {
      return [133, 77, 14];
    }

    if (value < 100) {
      return [154, 52, 18];
    }

    return [153, 27, 27];
  }

  private integer(
    value: number,
  ): string {
    const normalized =
      Number.isFinite(Number(value))
        ? Number(value)
        : 0;

    return new Intl.NumberFormat(
      'es-MX',
      {
        maximumFractionDigits: 0,
      },
    ).format(normalized);
  }

  private percentage(
    value: number,
  ): string {
    const normalized =
      Number.isFinite(Number(value))
        ? Number(value)
        : 0;

    return `${normalized.toFixed(1)}%`;
  }

  private pdfText(
    value: string,
  ): string {
    return String(value || '')
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .replace(/[–—]/g, '-')
      .replace(/\u00a0/g, ' ')
      .trim();
  }

  private filename(
    monthFromValue: string,
    monthToValue: string,
  ): string {
    const validMonthPattern =
      /^\d{4}-\d{2}$/;

    const safeMonthFrom =
      validMonthPattern.test(monthFromValue)
        ? monthFromValue
        : 'inicio';

    const safeMonthTo =
      validMonthPattern.test(monthToValue)
        ? monthToValue
        : 'fin';

    const safePeriod =
      safeMonthFrom === safeMonthTo
        ? safeMonthFrom
        : `${safeMonthFrom}_a_${safeMonthTo}`;

    return (
      'control_rutinas_asignacion_'
      + `${safePeriod}.pdf`
    );
  }
}

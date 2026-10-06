import {
  PurchaseRequisition,
  PurchaseRequisitionAttachment,
  PurchaseRequisitionEvent,
  PurchaseRequisitionItem,
} from './purchase-requisition.service';

export interface PurchaseRequisitionExportRow {
  requisition: PurchaseRequisition;
  branchName: string;
}

const HEADER_FILL = 'FF1F2937';
const HEADER_FONT = 'FFFFFFFF';
const BORDER_COLOR = 'FFD1D5DB';
const TITLE_FILL = 'FF111827';

export async function exportPurchaseRequisitionsWorkbook(
  rows: PurchaseRequisitionExportRow[],
): Promise<void> {
  if (!rows.length) {
    return;
  }

  const excel = await import('exceljs');
  const workbook = new excel.Workbook();

  workbook.creator = 'Suite Ultra';
  workbook.company = 'Ultra Gym';
  workbook.created = new Date();

  writeRequisitionsSheet(workbook, rows);
  writeItemsSheet(workbook, rows);
  writeEventsSheet(workbook, rows);
  writeAttachmentsSheet(workbook, rows);

  const buffer = await workbook.xlsx.writeBuffer();
  downloadWorkbook(
    buffer as BlobPart,
    buildFilename(),
  );
}

function writeRequisitionsSheet(workbook: any, rows: PurchaseRequisitionExportRow[]): void {
  const sheet = workbook.addWorksheet('Requisiciones', {
    views: [{ state: 'frozen', ySplit: 2 }],
  });

  sheet.addRow(['REQUISICIONES · SUITE ULTRA']);
  sheet.mergeCells('A1:U1');
  styleTitle(sheet.getCell('A1'));

  const headers = [
    'ID',
    'Folio',
    'Sucursal ID',
    'Sucursal',
    'Creada por usuario ID',
    'Categoría',
    'Motivo',
    'Justificación',
    'Prioridad',
    'Estado',
    'Aprobada por usuario ID',
    'Fecha aprobación',
    'Comentario aprobación',
    'Fecha rechazo',
    'Fecha creación',
    'Última actualización',
    'Partidas',
    'Eventos',
    'Adjuntos',
    'Total unidades',
    'Último evento',
  ];

  sheet.addRow(headers);
  styleHeaderRow(sheet.getRow(2));

  for (const row of rows) {
    const requisition = row.requisition;
    const items = requisition.items || [];
    const events = requisition.events || [];
    const attachments = requisition.attachments || [];

    sheet.addRow([
      requisition.id,
      requisition.public_id,
      requisition.sucursal_id,
      row.branchName,
      requisition.created_by_user_id,
      requisition.category,
      reasonLabel(requisition.reason),
      requisition.justification,
      priorityLabel(requisition.priority),
      statusLabel(requisition.status),
      requisition.approved_by_user_id ?? null,
      excelDate(requisition.approved_at),
      requisition.approval_comment ?? '',
      excelDate(requisition.rejected_at),
      excelDate(requisition.created_at),
      excelDate(requisition.updated_at),
      items.length,
      events.length,
      attachments.length,
      items.reduce((sum, item) => sum + Number(item.quantity || 0), 0),
      events.length ? eventLabel(events[events.length - 1].event_type) : '',
    ]);
  }

  configureColumns(sheet, [
    10, 20, 12, 24, 20, 20, 18, 48, 12, 24, 22,
    21, 36, 21, 21, 21, 10, 10, 10, 14, 26,
  ]);
  applyDateFormat(sheet, ['L', 'N', 'O', 'P'], 3, sheet.rowCount);
  applyBodyStyle(sheet, 3, sheet.rowCount, headers.length);
  sheet.autoFilter = 'A2:U' + sheet.rowCount;
}

function writeItemsSheet(workbook: any, rows: PurchaseRequisitionExportRow[]): void {
  const sheet = workbook.addWorksheet('Partidas', {
    views: [{ state: 'frozen', ySplit: 2 }],
  });

  sheet.addRow(['PARTIDAS POR REQUISICIÓN']);
  sheet.mergeCells('A1:H1');
  styleTitle(sheet.getCell('A1'));

  const headers = [
    'Folio',
    'Requisición ID',
    'Partida ID',
    'Descripción',
    'Cantidad',
    'Notas',
    'Fecha creación',
    'Sucursal',
  ];
  sheet.addRow(headers);
  styleHeaderRow(sheet.getRow(2));

  for (const row of rows) {
    for (const item of row.requisition.items || []) {
      addItemRow(sheet, row, item);
    }
  }

  configureColumns(sheet, [20, 14, 12, 44, 12, 36, 21, 24]);
  applyDateFormat(sheet, ['G'], 3, sheet.rowCount);
  applyBodyStyle(sheet, 3, sheet.rowCount, headers.length);
  sheet.autoFilter = 'A2:H' + Math.max(2, sheet.rowCount);
}

function writeEventsSheet(workbook: any, rows: PurchaseRequisitionExportRow[]): void {
  const sheet = workbook.addWorksheet('Historial', {
    views: [{ state: 'frozen', ySplit: 2 }],
  });

  sheet.addRow(['HISTORIAL DE REQUISICIONES']);
  sheet.mergeCells('A1:K1');
  styleTitle(sheet.getCell('A1'));

  const headers = [
    'Folio',
    'Requisición ID',
    'Evento ID',
    'Evento',
    'Actor usuario ID',
    'Estado anterior',
    'Estado nuevo',
    'Comentario',
    'Metadata JSON',
    'Fecha evento',
    'Sucursal',
  ];
  sheet.addRow(headers);
  styleHeaderRow(sheet.getRow(2));

  for (const row of rows) {
    for (const event of row.requisition.events || []) {
      addEventRow(sheet, row, event);
    }
  }

  configureColumns(sheet, [20, 14, 12, 28, 18, 22, 22, 44, 48, 21, 24]);
  applyDateFormat(sheet, ['J'], 3, sheet.rowCount);
  applyBodyStyle(sheet, 3, sheet.rowCount, headers.length);
  sheet.autoFilter = 'A2:K' + Math.max(2, sheet.rowCount);
}

function writeAttachmentsSheet(workbook: any, rows: PurchaseRequisitionExportRow[]): void {
  const sheet = workbook.addWorksheet('Adjuntos', {
    views: [{ state: 'frozen', ySplit: 2 }],
  });

  sheet.addRow(['METADATA DE ADJUNTOS']);
  sheet.mergeCells('A1:L1');
  styleTitle(sheet.getCell('A1'));

  const headers = [
    'Folio',
    'Requisición ID',
    'Adjunto ID',
    'Evento ID',
    'Tipo',
    'Archivo',
    'MIME',
    'Tamaño bytes',
    'SHA-256',
    'Subido por usuario ID',
    'Fecha creación',
    'Fecha eliminación',
  ];
  sheet.addRow(headers);
  styleHeaderRow(sheet.getRow(2));

  for (const row of rows) {
    for (const attachment of row.requisition.attachments || []) {
      addAttachmentRow(sheet, row, attachment);
    }
  }

  configureColumns(sheet, [20, 14, 12, 12, 16, 42, 24, 16, 68, 22, 21, 21]);
  applyDateFormat(sheet, ['K', 'L'], 3, sheet.rowCount);
  applyBodyStyle(sheet, 3, sheet.rowCount, headers.length);
  sheet.autoFilter = 'A2:L' + Math.max(2, sheet.rowCount);
}

function addItemRow(
  sheet: any,
  row: PurchaseRequisitionExportRow,
  item: PurchaseRequisitionItem,
): void {
  sheet.addRow([
    row.requisition.public_id,
    row.requisition.id,
    item.id ?? null,
    item.item_description,
    item.quantity,
    item.notes ?? '',
    excelDate(item.created_at),
    row.branchName,
  ]);
}

function addEventRow(
  sheet: any,
  row: PurchaseRequisitionExportRow,
  event: PurchaseRequisitionEvent,
): void {
  sheet.addRow([
    row.requisition.public_id,
    row.requisition.id,
    event.id,
    eventLabel(event.event_type),
    event.actor_user_id ?? null,
    event.from_status ? statusLabel(event.from_status) : '',
    event.to_status ? statusLabel(event.to_status) : '',
    event.comment ?? '',
    event.metadata_json ? JSON.stringify(event.metadata_json) : '',
    excelDate(event.created_at),
    row.branchName,
  ]);
}

function addAttachmentRow(
  sheet: any,
  row: PurchaseRequisitionExportRow,
  attachment: PurchaseRequisitionAttachment,
): void {
  sheet.addRow([
    row.requisition.public_id,
    row.requisition.id,
    attachment.id,
    attachment.event_id ?? null,
    attachmentTypeLabel(attachment.attachment_type),
    attachment.original_filename,
    attachment.mime_type,
    attachment.size_bytes,
    attachment.sha256,
    attachment.uploaded_by_user_id ?? null,
    excelDate(attachment.created_at),
    excelDate(attachment.deleted_at),
  ]);
}

function styleTitle(cell: any): void {
  cell.fill = {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb: TITLE_FILL },
  };
  cell.font = {
    name: 'Calibri',
    size: 15,
    bold: true,
    color: { argb: HEADER_FONT },
  };
  cell.alignment = {
    horizontal: 'left',
    vertical: 'middle',
  };
}

function styleHeaderRow(row: any): void {
  row.height = 26;
  row.eachCell((cell: any) => {
    cell.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: HEADER_FILL },
    };
    cell.font = {
      name: 'Calibri',
      size: 10,
      bold: true,
      color: { argb: HEADER_FONT },
    };
    cell.alignment = {
      horizontal: 'center',
      vertical: 'middle',
      wrapText: true,
    };
    cell.border = thinBorder();
  });
}

function applyBodyStyle(
  sheet: any,
  firstRow: number,
  lastRow: number,
  columnCount: number,
): void {
  for (let rowNumber = firstRow; rowNumber <= lastRow; rowNumber += 1) {
    for (let column = 1; column <= columnCount; column += 1) {
      const cell = sheet.getCell(rowNumber, column);
      cell.font = {
        name: 'Calibri',
        size: 10,
      };
      cell.alignment = {
        vertical: 'top',
        wrapText: true,
      };
      cell.border = thinBorder();
    }
  }
}

function thinBorder(): any {
  const side = {
    style: 'thin',
    color: { argb: BORDER_COLOR },
  };
  return {
    top: side,
    left: side,
    bottom: side,
    right: side,
  };
}

function configureColumns(sheet: any, widths: number[]): void {
  widths.forEach((width, index) => {
    sheet.getColumn(index + 1).width = width;
  });
}

function applyDateFormat(
  sheet: any,
  columns: string[],
  firstRow: number,
  lastRow: number,
): void {
  for (const column of columns) {
    for (let row = firstRow; row <= lastRow; row += 1) {
      sheet.getCell(column + row).numFmt = 'dd/mm/yyyy hh:mm';
    }
  }
}

function excelDate(value?: string | null): Date | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    PENDING_REVIEW: 'Pendiente de revisión',
    NEEDS_INFO: 'Requiere información',
    REJECTED: 'Rechazada',
    IN_QUOTATION: 'En cotización',
    CLOSED: 'Cerrada',
  };
  return labels[value] || value;
}

function priorityLabel(value: string): string {
  const labels: Record<string, string> = {
    NORMAL: 'Normal',
    HIGH: 'Alta',
    CRITICAL: 'Crítica',
  };
  return labels[value] || value;
}

function reasonLabel(value: string): string {
  const labels: Record<string, string> = {
    REPLACEMENT: 'Reemplazo',
    NEW_EQUIPMENT: 'Equipo nuevo',
    DAMAGE: 'Daño',
    EXPANSION: 'Expansión',
    OTHER: 'Otro',
  };
  return labels[value] || value;
}

function eventLabel(value: string): string {
  const labels: Record<string, string> = {
    CREATED: 'Creada',
    INFO_REQUESTED: 'Información solicitada',
    RESUBMITTED: 'Reenviada',
    APPROVED: 'Aprobada',
    REJECTED: 'Rechazada',
    ROUTED_TO_MAINTENANCE: 'Enviada a Mantenimiento',
    ATTACHMENT_ADDED: 'Adjunto agregado',
  };
  return labels[value] || value;
}

function attachmentTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    EVIDENCE: 'Evidencia',
    QUOTE: 'Cotización',
    OTHER: 'Otro',
  };
  return labels[value] || value;
}

function buildFilename(): string {
  const now = new Date();
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('-');

  return 'requisiciones_' + date + '.xlsx';
}

function downloadWorkbook(buffer: BlobPart, filename: string): void {
  const blob = new Blob(
    [buffer],
    {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    },
  );
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');

  anchor.href = url;
  anchor.download = filename;
  anchor.click();

  URL.revokeObjectURL(url);
}

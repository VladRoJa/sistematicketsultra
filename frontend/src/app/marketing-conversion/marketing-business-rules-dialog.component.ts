import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

interface MarketingBusinessRule {
  title: string;
  triggerLabel: string;
  trigger: string;
  note?: string;
}

interface MarketingDerivedRule {
  title: string;
  formula: string;
}

@Component({
  selector: 'app-marketing-business-rules-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: './marketing-business-rules-dialog.component.html',
  styleUrls: ['./marketing-business-rules-dialog.component.css'],
})
export class MarketingBusinessRulesDialogComponent {
  readonly primaryRules: MarketingBusinessRule[] = [
    {
      title: 'Inversión',
      triggerLabel: 'Aumenta cuando',
      trigger:
        'Meta registra gasto en una campaña y los contactos relacionados ' +
        'con sus anuncios permiten identificar una sola sucursal. Se suma ' +
        'el gasto completo de esa campaña.',
      note:
        'Si no se puede identificar una sucursal, o la evidencia apunta a ' +
        'más de una, ese gasto no se suma a la inversión de una sucursal.',
    },
    {
      title: 'Leads',
      triggerLabel: 'Aumenta +1 cuando',
      trigger:
        'existe un contacto único en iVentas que tiene un primer mensaje ' +
        'registrado y al menos una etiqueta que lo relaciona con un anuncio ' +
        'de Meta.',
      note:
        'Si el mismo contacto está relacionado con varios anuncios, sigue ' +
        'contando como 1 lead.',
    },
    {
      title: 'Visitantes',
      triggerLabel: 'Aumenta +1 cuando',
      trigger:
        'existe un teléfono único por sucursal asociado a un Pase recorrido ' +
        'o Pase 2 días gratis, con importe de $0 y que no esté cancelado ' +
        'o anulado.',
      note:
        'Varias visitas del mismo teléfono en la misma sucursal siguen ' +
        'contando como 1 visitante.',
    },
    {
      title: 'Ventas atribuidas',
      triggerLabel: 'Aumenta +1 cuando',
      trigger:
        'una venta tiene el mismo teléfono y la misma sucursal que un ' +
        'visitante, y la compra ocurre desde el día de la visita hasta un ' +
        'máximo de 30 días después.',
      note:
        'Una venta con importe de $0 puede contar como venta atribuida, ' +
        'aunque no aumente el ingreso.',
    },
    {
      title: 'Ingreso atribuido',
      triggerLabel: 'Aumenta por el importe pagado cuando',
      trigger:
        'una venta cumple las condiciones para ser una Venta atribuida. ' +
        'Se suma el importe pagado de esa venta.',
      note:
        'Un importe de $0 no cambia el ingreso. Un importe negativo reduce ' +
        'el total de ingreso atribuido.',
    },
  ];

  readonly derivedRules: MarketingDerivedRule[] = [
    {
      title: 'Costo por lead',
      formula: 'Inversión ÷ Leads',
    },
    {
      title: 'Costo por visita',
      formula: 'Inversión ÷ Visitantes',
    },
    {
      title: 'Costo por venta',
      formula: 'Inversión ÷ Ventas atribuidas',
    },
    {
      title: 'Lead → Visita',
      formula: 'Visitantes ÷ Leads',
    },
    {
      title: 'Visita → Venta',
      formula: 'Ventas atribuidas ÷ Visitantes',
    },
    {
      title: 'Lead → Venta',
      formula: 'Ventas atribuidas ÷ Leads',
    },
  ];
}

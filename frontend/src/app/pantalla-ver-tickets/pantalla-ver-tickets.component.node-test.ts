import '@angular/compiler';
import { HttpHeaders, HttpParams, HttpResponse } from '@angular/common/http';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { EMPTY, Observable, of, Subject } from 'rxjs';

import {
  DescargaReporteMantenimiento,
  MantenimientoEquiposService,
  RegionReporteMantenimientoDTO,
} from '../services/mantenimiento-equipos.service';
import { PantallaVerTicketsComponent } from './pantalla-ver-tickets.component';

interface HttpRequestRecord {
  url: string;
  options?: {
    params?: HttpParams;
    responseType?: string;
    observe?: string;
  };
}

class HttpClientStub {
  readonly requests: HttpRequestRecord[] = [];

  get(url: string, options?: HttpRequestRecord['options']) {
    this.requests.push({ url, options });

    if (url.endsWith('/reporte')) {
      const alcance = options?.params?.get('region_id')
        ? 'reg_mexicali'
        : 'todo';
      return of(new HttpResponse({
        body: new Blob(['xlsx']),
        headers: new HttpHeaders({
          'Content-Disposition':
            `attachment; filename=reporte_mantenimiento_equipos_${alcance}_02-sep-26.xlsx`,
        }),
      }));
    }

    return of([]);
  }
}

class MantenimientoEquiposServiceStub {
  readonly downloadRegionIds: Array<number | undefined> = [];
  regiones: RegionReporteMantenimientoDTO[] = [];
  downloadResult: Observable<DescargaReporteMantenimiento> = EMPTY;

  obtenerRegionesReporte() {
    return of(this.regiones);
  }

  descargarReporte(regionId?: number) {
    this.downloadRegionIds.push(regionId);
    return this.downloadResult;
  }
}

function createComponent(service: MantenimientoEquiposServiceStub) {
  const component = new PantallaVerTicketsComponent(
    {} as never,
    {} as never,
    {} as never,
    {} as never,
    {} as never,
    {} as never,
    {} as never,
    {} as never,
    {} as never,
    service as unknown as MantenimientoEquiposService,
    {} as never,
    {} as never,
  );
  component.user = { username: 'ADMICORP' };
  return component;
}

test('el service omite region_id para Todo y lo envía para una región', () => {
  const http = new HttpClientStub();
  const service = new MantenimientoEquiposService(http as never);
  const nombres: string[] = [];

  service.descargarReporte().subscribe((descarga) => {
    nombres.push(descarga.nombreArchivo);
  });
  service.descargarReporte(7).subscribe((descarga) => {
    nombres.push(descarga.nombreArchivo);
  });

  assert.equal(http.requests.length, 2);
  assert.equal(http.requests[0].url.endsWith('/reporte'), true);
  assert.equal(http.requests[0].options?.params?.has('region_id'), false);
  assert.equal(http.requests[1].options?.params?.get('region_id'), '7');
  assert.equal(http.requests[1].options?.responseType, 'blob');
  assert.equal(http.requests[1].options?.observe, 'response');
  assert.deepEqual(nombres, [
    'reporte_mantenimiento_equipos_todo_02-sep-26.xlsx',
    'reporte_mantenimiento_equipos_reg_mexicali_02-sep-26.xlsx',
  ]);
});

test('el service obtiene las regiones desde el catálogo backend', () => {
  const http = new HttpClientStub();
  const service = new MantenimientoEquiposService(http as never);

  service.obtenerRegionesReporte().subscribe();

  assert.equal(http.requests.length, 1);
  assert.equal(http.requests[0].url.endsWith('/regiones'), true);
});

test('el componente prepara opciones dinámicas sin duplicar Región', () => {
  const service = new MantenimientoEquiposServiceStub();
  service.regiones = [
    { id: 1, nombre: 'Región Norte' },
    { id: 2, nombre: 'Mexicali' },
  ];
  const component = createComponent(service);

  (component as any).cargarRegionesReporteMantenimiento();

  assert.deepEqual(
    component.regionesReporteMantenimiento,
    [
      { id: 1, nombre: 'Región Norte', etiqueta: 'Región Norte' },
      { id: 2, nombre: 'Mexicali', etiqueta: 'Región Mexicali' },
    ],
  );
});

test('Todo y región llaman al service con el alcance correcto', () => {
  const service = new MantenimientoEquiposServiceStub();
  const component = createComponent(service);

  component.descargarReporteMantenimiento();
  component.descargarReporteMantenimiento({ id: 8, nombre: 'Sur' });

  assert.deepEqual(service.downloadRegionIds, [undefined, 8]);
});

test('el componente usa sin cambios el nombre enviado por el backend', () => {
  const service = new MantenimientoEquiposServiceStub();
  const nombreArchivo =
    'reporte_mantenimiento_equipos_reg_san_luis_02-sep-26.xlsx';
  service.downloadResult = of({
    archivo: new Blob(['xlsx']),
    nombreArchivo,
  });
  const component = createComponent(service);
  const enlace = {
    href: '',
    download: '',
    clickCalled: false,
    click() {
      this.clickCalled = true;
    },
  };
  const originalDocument = (globalThis as any).document;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { createElement: () => enlace },
  });
  URL.createObjectURL = () => 'blob:reporte';
  URL.revokeObjectURL = () => undefined;

  try {
    component.descargarReporteMantenimiento({ id: 8, nombre: 'Región San Luis' });

    assert.equal(enlace.download, nombreArchivo);
    assert.equal(enlace.clickCalled, true);
  } finally {
    if (originalDocument === undefined) {
      delete (globalThis as any).document;
    } else {
      Object.defineProperty(globalThis, 'document', {
        configurable: true,
        value: originalDocument,
      });
    }
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
  }
});

test('loading permanece activo durante la descarga y se libera al completar', () => {
  const service = new MantenimientoEquiposServiceStub();
  const download = new Subject<DescargaReporteMantenimiento>();
  service.downloadResult = download;
  const component = createComponent(service);

  component.descargarReporteMantenimiento();
  assert.equal(component.descargandoReporteMantenimiento, true);

  download.complete();
  assert.equal(component.descargandoReporteMantenimiento, false);
});

test('loading se libera también cuando la descarga falla', () => {
  const alertas = require('../utils/alertas');
  const originalAlert = alertas.mostrarAlertaToast;
  alertas.mostrarAlertaToast = () => undefined;

  try {
    const service = new MantenimientoEquiposServiceStub();
    const download = new Subject<DescargaReporteMantenimiento>();
    service.downloadResult = download;
    const component = createComponent(service);

    component.descargarReporteMantenimiento();
    download.error({ status: 500 });

    assert.equal(component.descargandoReporteMantenimiento, false);
  } finally {
    alertas.mostrarAlertaToast = originalAlert;
  }
});

// src/app/inventario/catalogos/catalogos-routing.module.ts

import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { CatalogoCrudComponent } from './catalogo-crud.component';

const routes: Routes = [
  { path: 'marcas', component: CatalogoCrudComponent, data: { tipo: 'marcas', titulo: 'Marcas' } },
  { path: 'proveedores', component: CatalogoCrudComponent, data: { tipo: 'proveedores', titulo: 'Proveedores' } },
  { path: 'categorias', component: CatalogoCrudComponent, data: { tipo: 'categorias', titulo: 'Categorías' } },
  { path: 'unidades', component: CatalogoCrudComponent, data: { tipo: 'unidades', titulo: 'Unidades de Medida' } },
  { path: 'gruposmusculares', component: CatalogoCrudComponent, data: { tipo: 'gruposmusculares', titulo: 'Grupo muscular' } },
  { path: 'tipos', component: CatalogoCrudComponent, data: { tipo: 'tipos', titulo: 'Tipos de Inventario' } },


];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class CatalogosRoutingModule {}

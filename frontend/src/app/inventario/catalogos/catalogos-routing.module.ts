// src/app/inventario/catalogos/catalogos-routing.module.ts

import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { CatalogoCrudComponent } from './catalogo-crud.component';
import { AdminGuard } from 'src/app/guards/admin.guard';
import { ClasificacionCrudComponent } from './clasificacion-crud/clasificacion-crud.component';


const routes: Routes = [
    {
    path: '',
    canActivate: [AdminGuard],
    children: [
  
  { path: 'marcas', component: CatalogoCrudComponent, data: { tipo: 'marcas', titulo: 'Marcas' } },
  { path: 'proveedores', component: CatalogoCrudComponent, data: { tipo: 'proveedores', titulo: 'Proveedores' } },
  { path: 'clasificaciones', component: ClasificacionCrudComponent, data: { tipo: 'clasificaciones', titulo: 'Clasificaciones' } },
  { path: 'unidades', component: CatalogoCrudComponent, data: { tipo: 'unidades', titulo: 'Unidades de Medida' } },
  { path: 'gruposmusculares', component: CatalogoCrudComponent, data: { tipo: 'gruposmusculares', titulo: 'Grupo muscular' } },
  { path: 'tipos', component: CatalogoCrudComponent, data: { tipo: 'tipos', titulo: 'Tipos de Inventario' } },
  { path: 'categorias', component: CatalogoCrudComponent, data: { tipo: 'categorias', titulo: 'Categorias de Inventario' } },
  
    
  ]
    },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class CatalogosRoutingModule {}

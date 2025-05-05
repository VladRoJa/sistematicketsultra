// src/app/inventario/productos/productos.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { EditarProductoDialogComponent } from './editar-producto-dialog.component';
import { EliminarProductoDialogComponent } from './eliminar-producto-dialog.component';
import { ModalAgregarProductoComponent } from './modal-agregar-producto/modal-agregar-producto.component';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from 'src/app/utils/alertas';
import { MatTableDataSource } from '@angular/material/table';
import { MatPaginator } from '@angular/material/paginator';
import { ViewChild } from '@angular/core';
import * as XLSX from 'xlsx';
import * as FileSaver from 'file-saver';
import { MatPaginatorModule } from '@angular/material/paginator';
import { environment } from 'src/environments/environment';

@Component({
  selector: 'app-productos',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatTableModule,
    MatFormFieldModule,
    MatInputModule,
    FormsModule,
    MatButtonModule,
    EditarProductoDialogComponent,
    EliminarProductoDialogComponent,
    MatPaginatorModule
  ],
  templateUrl: './productos.component.html',
})
export class ProductosComponent implements OnInit {
  private http = inject(HttpClient);
  private dialog = inject(MatDialog);

  productos: any[] = [];
  dataSource = new MatTableDataSource<any>();
  columnasTabla = ['id', 'nombre', 'unidad', 'categoria', 'acciones'];
  nuevoProducto = {
    nombre: '',
    descripcion: '',
    unidad_medida: '',
    categoria: '',
    subcategoria: ''
  }
  
  filtros: any = {
    nombre: '',
    unidad_medida: '',
    categoria: ''
  };

  @ViewChild(MatPaginator) paginator!: MatPaginator;

  ngOnInit(): void {
    this.cargarProductos();
  }
  cargarProductos(): void {
    this.http.get<any[]>(`${environment.apiUrl}/inventario/productos`).subscribe({
      next: (data) => {
        this.dataSource.data = data;
        this.dataSource.paginator = this.paginator;
      },
      error: (error) => {
        console.error('Error al cargar productos', error);
      }
    });
  }

  aplicarFiltro(campo: string, valor: string) {
    this.filtros[campo] = valor.trim().toLowerCase();
  
    this.dataSource.filterPredicate = (data, _) => {
      return Object.keys(this.filtros).every((key) =>
        data[key]?.toString().toLowerCase().includes(this.filtros[key])
      );
    };
  
    this.dataSource.filter = Math.random().toString(); // Forzar cambio
  }
  

  agregarProducto(): void {
    const token = localStorage.getItem('token');
    if (!token) return alert('No autorizado');

    this.http.post(`${environment.apiUrl}/inventario/productos`, this.nuevoProducto, {
      headers: { Authorization: `Bearer ${token}` }
    }).subscribe({
      next: () => {
        this.cargarProductos();
        this.nuevoProducto = { nombre: '', descripcion: '', unidad_medida: '', categoria: '', subcategoria: '' };
      },
      error: (err) => {
        console.error('Error al agregar producto', err);
        alert('Error al agregar producto');
      }
    });
  }

  abrirDialogoEditar(producto: any): void {
    const dialogRef = this.dialog.open(EditarProductoDialogComponent, {
      width: '400px',
      data: { producto }
    });

    dialogRef.afterClosed().subscribe((resultado) => {
      if (resultado === 'actualizado') {
        this.cargarProductos();
      }
    });
  }

  abrirDialogoEliminar(producto: any): void {
    const dialogRef = this.dialog.open(EliminarProductoDialogComponent, {
      width: '350px',
      data: { nombre: producto.nombre }
    });

    dialogRef.afterClosed().subscribe((confirmado) => {
      if (confirmado) {
        this.eliminarProducto(producto.id);
      }
    });
  }

  eliminarProducto(id: number): void {
    const token = localStorage.getItem('token');
    if (!token) return alert('No autorizado');
  
    this.http.delete(`http://localhost:5000/api/inventario/productos/${id}`, {
      headers: { Authorization: `Bearer ${token}` }
    }).subscribe({
      next: () => {
        this.cargarProductos();
        mostrarAlertaToast('🗑️ Producto eliminado correctamente.');
      },
      error: (err) => {
        console.error('Error al eliminar producto', err);
        mostrarAlertaToast('❌ No se pudo eliminar el producto.', 'error');
      }
    });
  }
  
  abrirModalAgregarProducto(): void {
    const dialogRef = this.dialog.open(ModalAgregarProductoComponent, {
      width: '500px',
      panelClass: 'custom-modal-animado'
    });
  
    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        const token = localStorage.getItem('token');
        if (!token) return alert('No autorizado');
  
        // 🔁 Convertimos el campo `unidad` a `unidad_medida`
        const productoAGuardar = {
          nombre: result.nombre,
          descripcion: result.descripcion,
          categoria: result.categoria,
          subcategoria: result.subcategoria,
          unidad_medida: result.unidad  // ← este es el campo correcto para backend
        };
  
        this.http.post(`${environment.apiUrl}/inventario/productos`, productoAGuardar, {
          headers: { Authorization: `Bearer ${token}` }
        }).subscribe({
          next: () => {
            this.cargarProductos();
            mostrarAlertaToast('✅ Producto agregado correctamente.');
          },
          error: (err) => {
            console.error('Error al agregar producto', err);
            mostrarAlertaErrorDesdeStatus(err.status);
          }
        });
      }
    });
  }
  exportarAExcel(): void {
    const ws = XLSX.utils.json_to_sheet(this.dataSource.filteredData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Productos');
  
    const excelBuffer: any = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
    const blobData = new Blob([excelBuffer], { type: 'application/octet-stream' });
    FileSaver.saveAs(blobData, `productos_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }
  
}

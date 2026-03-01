import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { AdminUsuariosService } from '../../services/admin-usuarios.service';
import { Router } from '@angular/router';

type SucursalOption = { id: number; nombre: string };
type UsuarioOption = { id: number; username: string; rol: string; sucursal_id: number };


@Component({
  selector: 'app-admin-usuarios-sucursales',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './admin-usuarios-sucursales.component.html',
})
export class AdminUsuariosSucursalesComponent implements OnInit {
  form: FormGroup;

  private cargarCatalogoSucursales(): void {
    this.loading = true;
    this.errorMsg = null;

    this.http
      .get<Array<{ sucursal_id: number; sucursal: string }>>('/api/sucursales/listar')
      .subscribe({
        next: (rows) => {
          this.sucursales = (rows ?? []).map(r => ({
            id: Number(r.sucursal_id),
            nombre: String(r.sucursal),
          }));
          this.loading = false;
        },
        error: (err) => {
          this.loading = false;
          this.errorMsg = err?.error?.mensaje ?? 'Error al cargar catálogo de sucursales';
        },
      });
  }

userId: number | null = null;

// Propiedades para manejo de estado UI
  
  loading = false;
  errorMsg: string | null = null;
  okMsg: string | null = null;
  sucursales: Array<{ id: number; nombre: string }> = [];
  username: string | null = null;


  usuarios: UsuarioOption[] = [];
  usuariosFiltrados: UsuarioOption[] = [];
  busquedaUsuario = '';
  selectedUserIdForNav: number | null = null;

  constructor(
    private fb: FormBuilder,
    private adminUsuariosService: AdminUsuariosService,
    private http: HttpClient,
    private route: ActivatedRoute,
    private router: Router
  ) {
    this.form = this.fb.group({
      sucursales_ids: this.fb.control<number[]>([]),
    });
  }

ngOnInit(): void {
  this.route.paramMap.subscribe(params => {
    const raw = params.get('userId');
    const userId = raw ? Number(raw) : NaN;

    if (!raw || Number.isNaN(userId)) {
      this.userId = null;{}
      this.errorMsg = 'Ruta inválida: userId no es numérico';
      return;
    }

    this.userId = userId;
    this.cargarUsuario();


    // reset mensajes
    this.errorMsg = null;
    this.okMsg = null;

    // Cargar catálogo si aún no está cargado (para no pegarle cada vez)
    if (this.sucursales.length === 0) {
      this.cargarCatalogoSucursales();
    }

    // Siempre recargar asignadas al cambiar userId
    this.cargarSucursalesAsignadas();
  });
}

  get selectedIds(): number[] {
    return (this.form.value.sucursales_ids ?? []) as number[];
  }

  isSucursalSeleccionada(id: number): boolean {
    return this.selectedIds.includes(id);
  }

  toggleSucursal(id: number): void {
    const next = this.isSucursalSeleccionada(id)
      ? this.selectedIds.filter(x => x !== id)
      : [...this.selectedIds, id];

    this.form.patchValue({ sucursales_ids: next });
  }

  cargarSucursalesAsignadas(): void {
    if (this.userId === null) {
        this.errorMsg = 'No hay userId seleccionado';
        return;
      }

    this.loading = true;
    this.errorMsg = null;
    this.okMsg = null;

    this.adminUsuariosService.getSucursalesDeUsuario(this.userId).subscribe({
      next: (resp) => {
        this.form.patchValue({ sucursales_ids: resp.sucursales_ids ?? [] });
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = err?.error?.mensaje ?? 'Error al cargar sucursales del usuario';
      },
    });
  }

  private cargarUsuario(): void {
    if (this.userId === null) {
      this.username = null;
      return;
    }

    this.http
      .get<{ id: number; username: string; rol: string; sucursal_id: number }>(`/api/usuarios/${this.userId}`)
      .subscribe({
        next: (u) => {
          this.username = u?.username ?? null;  
        },
        error: () => {
          this.username = null;
        },
      });
  }

  aplicar(): void {
    if (this.userId === null) {
        this.errorMsg = 'No hay userId seleccionado';
        return;
      }
    this.loading = true;
    this.errorMsg = null;
    this.okMsg = null;

    this.adminUsuariosService.actualizarSucursalesDeUsuario(this.userId, {
      sucursales_ids: this.selectedIds,
    }).subscribe({
      next: (resp) => {
        this.form.patchValue({ sucursales_ids: resp.sucursales_ids ?? [] });
        this.loading = false;
        this.okMsg = 'Cambios guardados';
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = err?.error?.mensaje ?? 'Error al guardar sucursales';
      },
    });
  }


  aplicarFiltroUsuarios(): void {
    const q = (this.busquedaUsuario || '').trim().toLowerCase();

    if (!q) {
      this.usuariosFiltrados = [...this.usuarios];
      return;
    }

    this.usuariosFiltrados = this.usuarios.filter(u =>
      u.username.toLowerCase().includes(q) ||
      u.rol.toLowerCase().includes(q) ||
      String(u.sucursal_id).includes(q) ||
      String(u.id).includes(q)
    );
  }

  irAUsuarioSeleccionado(): void {
  if (!this.selectedUserIdForNav) return;

  // Con hash routing, Router navega bien (lo del # lo maneja Angular)
  this.router.navigate(['admin-usuarios-sucursales', this.selectedUserIdForNav]);
}

}
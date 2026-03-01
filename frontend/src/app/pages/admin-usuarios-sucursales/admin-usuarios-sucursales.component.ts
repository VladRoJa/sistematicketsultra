import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { environment } from 'src/environments/environment';

import { AdminUsuariosService } from '../../services/admin-usuarios.service';

type UsuarioOption = { id: number; username: string; rol: string; sucursal_id: number };

@Component({
  selector: 'app-admin-usuarios-sucursales',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule],
  templateUrl: './admin-usuarios-sucursales.component.html',
})
export class AdminUsuariosSucursalesComponent implements OnInit {
  // ─────────────────────────────────────────────────────────────
  // Form
  // ─────────────────────────────────────────────────────────────
  form: FormGroup;

  // ─────────────────────────────────────────────────────────────
  // Estado del componente
  // ─────────────────────────────────────────────────────────────
  userId: number | null = null;

  loading = false;
  errorMsg: string | null = null;
  okMsg: string | null = null;

  // Catálogo de sucursales para dibujar checkboxes/lista
  sucursales: Array<{ id: number; nombre: string }> = [];

  // UI: nombre del usuario seleccionado por route :userId
  public username: string | null = null;
  
  // Base URL API (según environment)
  private readonly API_BASE_URL = environment.apiUrl;

  // (Opcional, si tienes UI para buscar/navegar entre usuarios)
  usuarios: UsuarioOption[] = [];
  usuariosFiltrados: UsuarioOption[] = [];
  busquedaUsuario = '';
  selectedUserIdForNav: number | null = null;

  constructor(
    private readonly fb: FormBuilder,
    private readonly adminUsuariosService: AdminUsuariosService,
    private readonly http: HttpClient,
    private readonly route: ActivatedRoute,
    private readonly router: Router,
  ) {
    this.form = this.fb.group({
      // Lista de IDs seleccionados
      sucursales_ids: this.fb.control<number[]>([]),
    });
  }

  // ─────────────────────────────────────────────────────────────
  // Lifecycle
  // ─────────────────────────────────────────────────────────────
ngOnInit(): void {
  /**
   * Reacciona a cambios de route :userId
   * Ej: /admin-usuarios-sucursales/123
   */
  this.route.paramMap.subscribe((params) => {
    const raw = params.get('userId');

    // Reset mensajes por cada navegación
    this.errorMsg = null;
    this.okMsg = null;

    // ✅ Caso 1: ruta SIN userId -> modo entrada (NO es error)
    if (!raw) {
      this.userId = null;
      this.username = null;

      this.cargarUsuarios();

      // (Opcional) precargar catálogo para que la pantalla no se vea vacía
      if (this.sucursales.length === 0) {
        this.cargarCatalogoSucursales();
      }
      return;
    }

    // ✅ Caso 2: ruta CON userId -> validar
    const userId = Number(raw);
    if (Number.isNaN(userId) || userId <= 0) {
      this.userId = null;
      this.username = null;
      this.errorMsg = 'Ruta inválida: userId no es numérico';
      return;
    }

    // Set de user seleccionado
    this.userId = userId;

    // 1) Cargar usuario (solo username para UI)
    this.cargarUsuario();

    // 2) Cargar catálogo de sucursales solo si no está cargado
    if (this.sucursales.length === 0) {
      this.cargarCatalogoSucursales();
    }

    // 3) Cargar sucursales asignadas al usuario
    this.cargarSucursalesAsignadas();
  });
}

  // ─────────────────────────────────────────────────────────────
  // Helpers para UI de selección
  // ─────────────────────────────────────────────────────────────
  get selectedIds(): number[] {
    return (this.form.value.sucursales_ids ?? []) as number[];
  }

  isSucursalSeleccionada(id: number): boolean {
    return this.selectedIds.includes(id);
  }

  toggleSucursal(id: number): void {
    const next = this.isSucursalSeleccionada(id)
      ? this.selectedIds.filter((x) => x !== id)
      : [...this.selectedIds, id];

    this.form.patchValue({ sucursales_ids: next });
  }

  // ─────────────────────────────────────────────────────────────
  // Data loading
  // ─────────────────────────────────────────────────────────────
  /**
   * Catálogo de sucursales (para mostrar checkboxes)
   */
  private cargarCatalogoSucursales(): void {
    this.loading = true;
    this.errorMsg = null;

    // Nota: aquí estás usando proxy relativo /api/...
    // Lo respetamos tal cual.
    this.http
      .get<Array<{ sucursal_id: number; sucursal: string }>>('/api/sucursales/listar')
      .subscribe({
        next: (rows) => {
          this.sucursales = (rows ?? []).map((r) => ({
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

  /**
   * Trae sucursales asignadas del usuario y las pone en el form
   */
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

  /**
   * Trae datos del usuario seleccionado (por ahora solo username)
   */
  private cargarUsuario(): void {
    if (this.userId === null) {
      this.username = null;
      return;
    }

    // Aquí usamos API_BASE_URL (para que quede consistente con env)
    this.http
      .get<{ id: number; username: string; rol: string; sucursal_id: number }>(
        `${this.API_BASE_URL}/usuarios/${this.userId}`,
      )
      .subscribe({
        next: (u) => {
          this.username = u?.username ?? null;
        },
        error: () => {
          this.username = null;
        },
      });
  }

  private cargarUsuarios(): void {
    this.loading = true;
    this.errorMsg = null;

    this.http.get<UsuarioOption[]>(`${this.API_BASE_URL}/usuarios`).subscribe({
      next: (rows) => {
        this.usuarios = rows ?? [];
        this.usuariosFiltrados = [...this.usuarios];
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = err?.error?.mensaje ?? 'Error al cargar usuarios';
      },
    });
  }

  
  // ─────────────────────────────────────────────────────────────
  // Actions
  // ─────────────────────────────────────────────────────────────
  aplicar(): void {
    if (this.userId === null) {
      this.errorMsg = 'No hay userId seleccionado';
      return;
    }

    this.loading = true;
    this.errorMsg = null;
    this.okMsg = null;

    this.adminUsuariosService
      .actualizarSucursalesDeUsuario(this.userId, {
        sucursales_ids: this.selectedIds,
      })
      .subscribe({
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

  // ─────────────────────────────────────────────────────────────
  // (Opcional) Filtro de usuarios y navegación
  // ─────────────────────────────────────────────────────────────
  aplicarFiltroUsuarios(): void {
    const q = (this.busquedaUsuario || '').trim().toLowerCase();

    if (!q) {
      this.usuariosFiltrados = [...this.usuarios];
      return;
    }

    this.usuariosFiltrados = this.usuarios.filter((u) => {
      return (
        u.username.toLowerCase().includes(q) ||
        u.rol.toLowerCase().includes(q) ||
        String(u.sucursal_id).includes(q) ||
        String(u.id).includes(q)
      );
    });
  }

  irAUsuarioSeleccionado(): void {
    if (!this.selectedUserIdForNav) return;

    // Con hash routing, Angular lo resuelve
    this.router.navigate(['admin-usuarios-sucursales', this.selectedUserIdForNav]);
  }
}
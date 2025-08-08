import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-admin-panel',
  standalone: true,
  imports: [CommonModule, RouterModule, MatCardModule, MatButtonModule],
  templateUrl: './admin-panel.component.html',
  styleUrls: ['./admin-panel.component.css']
})
export class AdminPanelComponent implements OnInit {
  usuario: any = {};

  ngOnInit() {
    // Cárgalo desde AuthService si tienes, o localStorage como ejemplo
    this.usuario = {
      nombre: localStorage.getItem('nombre'),
      username: localStorage.getItem('username'),
      rol: localStorage.getItem('rol'),
      sucursal: localStorage.getItem('sucursal'),
    };
  }

  constructor(private router: Router) {}

  navegar(ruta: string) {
    this.router.navigate([ruta]);
  }
}

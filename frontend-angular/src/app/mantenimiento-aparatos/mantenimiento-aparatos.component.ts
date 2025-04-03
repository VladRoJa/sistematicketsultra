import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { JwtHelperService } from '@auth0/angular-jwt';

@Component({
  selector: 'app-mantenimiento-aparatos',
  templateUrl: './mantenimiento-aparatos.component.html',
  styleUrls: ['./mantenimiento-aparatos.component.css']
})
export class MantenimientoAparatosComponent implements OnInit {
  aparatos: any[] = [];
  form = {
    aparato_id: '',
    problema_detectado: '',
    necesita_refaccion: false
  };

  constructor(private http: HttpClient, private jwtHelper: JwtHelperService) {}

  ngOnInit(): void {
    const token = localStorage.getItem('token');
    if (token) {
      const decoded = this.jwtHelper.decodeToken(token);
      const sucursalId = decoded?.id_sucursal;

      if (sucursalId) {
        this.http.get<any[]>(`http://localhost:5000/api/aparatos/${sucursalId}`)
          .subscribe({
            next: data => this.aparatos = data,
            error: err => console.error('Error al obtener aparatos:', err)
          });
      }
    }
  }

  submitFormulario() {
    console.log('Formulario enviado:', this.form);

    // Aquí puedes hacer la petición POST para crear el ticket
    // por ahora solo lo dejamos como consola
  }
}

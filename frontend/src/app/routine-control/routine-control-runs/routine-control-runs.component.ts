import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { Router } from '@angular/router';
import { debounceTime } from 'rxjs/operators';
import { RoutineControlRun } from '../models/routine-control.models';
import { RoutineControlService } from '../services/routine-control.service';

@Component({
  selector: 'app-routine-control-runs', standalone: true,
  imports: [CommonModule, ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatPaginatorModule, MatSelectModule],
  templateUrl: './routine-control-runs.component.html', styleUrls: ['./routine-control-runs.component.css'],
})
export class RoutineControlRunsComponent implements OnInit {
  readonly statuses = ['PENDING', 'RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED', 'CANCELLED', 'REPLACED'];
  readonly form = this.fb.group({ status: [''], date_from: [''], date_to: [''] });
  runs: RoutineControlRun[] = []; total = 0; page = 1; pageSize = 25; loading = false; errorMessage = '';
  constructor(private readonly fb: FormBuilder, private readonly service: RoutineControlService, private readonly router: Router) {}
  ngOnInit(): void { this.form.valueChanges.pipe(debounceTime(250)).subscribe(() => { this.page = 1; this.load(); }); this.load(); }
  back(): void { this.router.navigate(['/control-rutinas']); }
  pageChanged(event: PageEvent): void { this.page = event.pageIndex + 1; this.pageSize = event.pageSize; this.load(); }
  load(): void { const value = this.form.getRawValue(); this.loading = true; this.errorMessage = ''; this.service.getRuns({ status: value.status || null, date_from: value.date_from || null, date_to: value.date_to || null, page: this.page, page_size: this.pageSize }).subscribe({ next: (result) => { this.runs = result.items; this.total = result.total; this.loading = false; }, error: () => { this.loading = false; this.errorMessage = 'No fue posible consultar el historial de corridas.'; } }); }
}

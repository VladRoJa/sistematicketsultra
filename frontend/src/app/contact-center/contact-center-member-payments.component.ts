import { CommonModule } from '@angular/common';
import { Component, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Subscription } from 'rxjs';

import {
  ContactCenterPaymentMember,
  ContactCenterService,
} from './contact-center.service';

@Component({
  selector: 'app-contact-center-member-payments',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  templateUrl: './contact-center-member-payments.component.html',
  styleUrls: ['./contact-center-member-payments.component.css'],
})
export class ContactCenterMemberPaymentsComponent implements OnDestroy {
  query = '';
  rows: ContactCenterPaymentMember[] = [];
  loading = false;
  searched = false;
  errorMessage = '';
  feedbackMessage = '';

  private searchSubscription: Subscription | null = null;

  constructor(private readonly contactCenter: ContactCenterService) {}

  search(): void {
    const term = this.query.trim();
    this.searchSubscription?.unsubscribe();
    this.rows = [];
    this.searched = false;
    this.errorMessage = '';
    this.feedbackMessage = '';

    if (term.length < 3 || term.length > 80) {
      this.loading = false;
      this.errorMessage = 'Ingresa al menos 3 caracteres (máximo 80).';
      return;
    }

    this.loading = true;
    this.searchSubscription = this.contactCenter.getMemberPayments(term).subscribe({
      next: (response) => {
        this.rows = response.rows;
        this.loading = false;
        this.searched = true;
      },
      error: (error) => {
        this.loading = false;
        this.errorMessage =
          error?.error?.mensaje || 'No fue posible buscar socios. Intenta de nuevo.';
      },
    });
  }

  async copyText(value: string, description: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      this.feedbackMessage = description + ' copiado al portapapeles.';
      this.errorMessage = '';
    } catch {
      this.feedbackMessage = '';
      this.errorMessage = 'No se pudo copiar automáticamente. Selecciona y copia el texto.';
    }
  }

  ngOnDestroy(): void {
    this.searchSubscription?.unsubscribe();
  }
}

// excel-filter-table.component.ts


import { Component, OnInit, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-excel-filter-table',
  templateUrl: './excel-filter-table.component.html',
  styleUrls: ['./excel-filter-table.component.css']
})
export class ExcelFilterTableComponent implements OnInit {
  @Input() data: any[] = []; // ✅ Recibe los datos desde el componente padre
  @Output() filterChange = new EventEmitter<any>(); // ✅ Emite los filtros seleccionados

  datosFiltrados: any[] = [];
  distinctValues: any[] = [];
  filteredValues: any[] = [];
  selectedFilters: Set<any> = new Set();
  activeFilterColumn: string | null = null;
  private backupSelection: Set<any> = new Set();

  ngOnInit() {
    this.cargarValoresUnicos();
    this.datosFiltrados = [...this.data];
  }

  cargarValoresUnicos() {
    this.distinctValues = [...new Set(this.data)];
    this.selectedFilters = new Set(this.distinctValues);
    this.filteredValues = [...this.distinctValues];
  }

  openFilter() {
    if (this.activeFilterColumn) {
      this.activeFilterColumn = null;
    } else {
      this.activeFilterColumn = "open";
      this.backupSelection = new Set(this.selectedFilters);
      this.filteredValues = [...this.distinctValues];
    }
  }

  onFilterSearch(searchText: string) {
    const lower = searchText.toLowerCase();
    this.filteredValues = this.distinctValues.filter(val =>
      val && val.toString().toLowerCase().includes(lower)
    );
  }

  onCheckboxChange(valor: any, checked: boolean) {
    if (checked) {
      this.selectedFilters.add(valor);
    } else {
      this.selectedFilters.delete(valor);
    }
  }

  applyFilter() {
    this.filterChange.emit([...this.selectedFilters]); // ✅ Enviar los valores filtrados
    this.activeFilterColumn = null;
  }

  cancelFilter() {
    this.selectedFilters = new Set(this.backupSelection);
    this.activeFilterColumn = null;
  }
}

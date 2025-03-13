import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ExcelFilterTableComponent } from './excel-filter-table-component';

describe('ExcelFilterTableComponentComponent', () => {
  let component: ExcelFilterTableComponent;
  let fixture: ComponentFixture<ExcelFilterTableComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExcelFilterTableComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ExcelFilterTableComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

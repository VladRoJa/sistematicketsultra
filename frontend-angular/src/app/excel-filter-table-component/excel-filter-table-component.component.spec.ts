import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ExcelFilterTableComponentComponent } from './excel-filter-table-component.component';

describe('ExcelFilterTableComponentComponent', () => {
  let component: ExcelFilterTableComponentComponent;
  let fixture: ComponentFixture<ExcelFilterTableComponentComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExcelFilterTableComponentComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ExcelFilterTableComponentComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

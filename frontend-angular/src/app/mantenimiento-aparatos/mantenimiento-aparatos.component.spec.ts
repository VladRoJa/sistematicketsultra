import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MantenimientoAparatosComponent } from './mantenimiento-aparatos.component';

describe('MantenimientoAparatosComponent', () => {
  let component: MantenimientoAparatosComponent;
  let fixture: ComponentFixture<MantenimientoAparatosComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [MantenimientoAparatosComponent]
    });
    fixture = TestBed.createComponent(MantenimientoAparatosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MantenimientoEdificioComponent } from './mantenimiento-edificio.component';

describe('MantenimientoEdificioComponent', () => {
  let component: MantenimientoEdificioComponent;
  let fixture: ComponentFixture<MantenimientoEdificioComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [MantenimientoEdificioComponent]
    });
    fixture = TestBed.createComponent(MantenimientoEdificioComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

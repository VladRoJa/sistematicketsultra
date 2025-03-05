import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsMantenimientoComponent } from './tickets-mantenimiento.component';

describe('TicketsMantenimientoComponent', () => {
  let component: TicketsMantenimientoComponent;
  let fixture: ComponentFixture<TicketsMantenimientoComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsMantenimientoComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsMantenimientoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

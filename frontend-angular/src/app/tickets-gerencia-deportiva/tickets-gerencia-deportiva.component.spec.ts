import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsGerenciaDeportivaComponent } from './tickets-gerencia-deportiva.component';

describe('TicketsGerenciaDeportivaComponent', () => {
  let component: TicketsGerenciaDeportivaComponent;
  let fixture: ComponentFixture<TicketsGerenciaDeportivaComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsGerenciaDeportivaComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsGerenciaDeportivaComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

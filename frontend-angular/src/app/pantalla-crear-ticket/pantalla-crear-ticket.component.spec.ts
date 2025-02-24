import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PantallaCrearTicketComponent } from './pantalla-crear-ticket.component';

describe('PantallaCrearTicketComponent', () => {
  let component: PantallaCrearTicketComponent;
  let fixture: ComponentFixture<PantallaCrearTicketComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PantallaCrearTicketComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PantallaCrearTicketComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

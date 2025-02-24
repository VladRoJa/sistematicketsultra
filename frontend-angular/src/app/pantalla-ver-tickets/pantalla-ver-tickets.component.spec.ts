import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PantallaVerTicketsComponent } from './pantalla-ver-tickets.component';

describe('PantallaVerTicketsComponent', () => {
  let component: PantallaVerTicketsComponent;
  let fixture: ComponentFixture<PantallaVerTicketsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PantallaVerTicketsComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PantallaVerTicketsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

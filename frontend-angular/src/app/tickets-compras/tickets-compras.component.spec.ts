import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsComprasComponent } from './tickets-compras.component';

describe('TicketsComprasComponent', () => {
  let component: TicketsComprasComponent;
  let fixture: ComponentFixture<TicketsComprasComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsComprasComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsComprasComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

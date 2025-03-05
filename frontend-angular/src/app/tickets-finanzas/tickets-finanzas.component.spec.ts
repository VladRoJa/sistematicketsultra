import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsFinanzasComponent } from './tickets-finanzas.component';

describe('TicketsFinanzasComponent', () => {
  let component: TicketsFinanzasComponent;
  let fixture: ComponentFixture<TicketsFinanzasComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsFinanzasComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsFinanzasComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsSistemasComponent } from './tickets-sistemas.component';

describe('TicketsSistemasComponent', () => {
  let component: TicketsSistemasComponent;
  let fixture: ComponentFixture<TicketsSistemasComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsSistemasComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsSistemasComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

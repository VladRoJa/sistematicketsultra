import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsRecursosHumanosComponent } from './tickets-recursos-humanos.component';

describe('TicketsRecursosHumanosComponent', () => {
  let component: TicketsRecursosHumanosComponent;
  let fixture: ComponentFixture<TicketsRecursosHumanosComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsRecursosHumanosComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsRecursosHumanosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

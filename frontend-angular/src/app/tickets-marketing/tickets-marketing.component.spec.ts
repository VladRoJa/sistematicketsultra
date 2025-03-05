import { ComponentFixture, TestBed } from '@angular/core/testing';

import { TicketsMarketingComponent } from './tickets-marketing.component';

describe('TicketsMarketingComponent', () => {
  let component: TicketsMarketingComponent;
  let fixture: ComponentFixture<TicketsMarketingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TicketsMarketingComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(TicketsMarketingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

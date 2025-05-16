import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ReportarErrorComponent } from './reportar-error.component';

describe('ReportarErrorComponent', () => {
  let component: ReportarErrorComponent;
  let fixture: ComponentFixture<ReportarErrorComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ReportarErrorComponent]
    });
    fixture = TestBed.createComponent(ReportarErrorComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

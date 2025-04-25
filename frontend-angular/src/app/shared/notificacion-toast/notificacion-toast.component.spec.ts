import { ComponentFixture, TestBed } from '@angular/core/testing';

import { NotificacionToastComponent } from './notificacion-toast.component';

describe('NotificacionToastComponent', () => {
  let component: NotificacionToastComponent;
  let fixture: ComponentFixture<NotificacionToastComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [NotificacionToastComponent]
    });
    fixture = TestBed.createComponent(NotificacionToastComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AdminPermisosComponent } from './admin-permisos.component';

describe('AdminPermisosComponent', () => {
  let component: AdminPermisosComponent;
  let fixture: ComponentFixture<AdminPermisosComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminPermisosComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(AdminPermisosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

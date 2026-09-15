import { Component } from '@angular/core';

import { MarketingReactivationComponent } from './marketing-reactivation.component';
import { MarketingCampaignDeliveryComponent } from './marketing-campaign-delivery.component';
import { MarketingReactivationOutcomesComponent } from './marketing-reactivation-outcomes.component';

@Component({
  selector: 'app-marketing-reactivation-page',
  standalone: true,
  imports: [
    MarketingReactivationComponent,
    MarketingCampaignDeliveryComponent,
    MarketingReactivationOutcomesComponent,
  ],
  templateUrl: './marketing-reactivation-page.component.html',
  styleUrls: ['./marketing-reactivation-page.component.css'],
})
export class MarketingReactivationPageComponent {}

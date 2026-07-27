import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from procurement.models import Tender, Bid
from procurement.views import BidAnalyzer, defaultdict, Decimal

tender = Tender.objects.get(id=1)
user_supplier_name = "Test Supplier" # assuming the user "Supplier" got their name bound to Test Supplier

from procurement.models import VolumeRequirement
vols = VolumeRequirement.objects.filter(tender=tender)
airport_map = defaultdict(list)
for v in vols:
    airport_map[v.airport.id].append(v)

for airport_id, vol_list in airport_map.items():
    airport = vol_list[0].airport
    bids_qs = Bid.objects.filter(tender=tender, round_number__lte=tender.current_round, airport=airport).order_by('supplier', 'airline', 'round_number')
    
    latest_bids = {}
    for b in bids_qs:
        latest_bids[f"{b.supplier.id}_{b.airline.id}"] = b
        
    bids_data = []
    for b in latest_bids.values():
        val = BidAnalyzer.analyze_bid(b, 'USD', None, tender, vol_list)
        val['supplier_name_eval'] = str(b.supplier)
        bids_data.append(val)
        
    bids_data.sort(key=lambda x: x['total_landed_cost'])
    
    print(f"--- AIRPORT {airport.icao_code} ---")
    for idx, bd in enumerate(bids_data):
        print(f"Rank {idx+1}: {bd['supplier_name_eval']} | Landed Cost: {bd['total_landed_cost']}")
        
    best = Decimal(str(bids_data[0]['total_landed_cost']))
    print("\n[Admin Gap Calculate]")
    for bid in bids_data:
        cost = Decimal(str(bid['total_landed_cost']))
        gap = ((cost - best) / best * Decimal(100)) if best != 0 else Decimal(0)
        print(f" - {bid['supplier_name_eval']}: Gap={gap}%")
        
    print("\n[Supplier Dashboard Gap Calculate]")
    total_bidders = len(bids_data)
    best_cost = Decimal(str(bids_data[0]['total_landed_cost']))
    second_best_cost = Decimal(str(bids_data[1]['total_landed_cost'])) if total_bidders > 1 else None
    
    for idx, bid in enumerate(bids_data):
        cost = Decimal(str(bid['total_landed_cost']))
        if idx == 0:
            if second_best_cost and second_best_cost > 0:
                gap = ((cost - second_best_cost) / second_best_cost * Decimal(100))
            else:
                gap = Decimal(0)
        else:
            if best_cost > 0:
                 gap = ((cost - best_cost) / best_cost * Decimal(100))
            else:
                 gap = Decimal(0)
        print(f" - {bid['supplier_name_eval']} Rank {idx+1}: Gap={gap}%")


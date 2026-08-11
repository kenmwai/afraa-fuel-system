from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Tender, VolumeRequirement, Bid, Currency, UnitOfMeasure, GlobalConfig, ExchangeRate, Airline, Supplier, Airport, SupplierDocument
from .Converters import BidAnalyzer
from .forms import UserRegistrationForm, SupplierDocumentForm
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import json

@login_required
def dashboard(request):
    tenders = Tender.objects.all().order_by('-start_date')
    context = {'tenders': tenders}
    if hasattr(request.user, 'supplier'):
        supplier = request.user.supplier
        context['supplier'] = supplier
        context['is_approved'] = supplier.is_approved_to_bid()
        context['has_uploaded_all'] = supplier.has_uploaded_all_required_docs()
        
        # Check specific document statuses
        docs = supplier.documents.all()
        doc_status_map = {doc.document_type: doc.status for doc in docs}
        context['business_registration_status'] = doc_status_map.get('business_registration', 'missing')
        context['insurance_status'] = doc_status_map.get('insurance', 'missing')
    return render(request, 'procurement/dashboard.html', context)

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            if user.email == 'kkionero@afraa.org':
                user.is_active = True
                user.is_staff = True
                user.is_superuser = True
            else:
                user.is_active = False # Require admin approval
            user.save()
            
            # Create corresponding profile
            account_type = form.cleaned_data.get('account_type')
            company_name = form.cleaned_data.get('company_name')
            
            if account_type == 'airline':
                Airline.objects.create(user=user, name=company_name)
            elif account_type == 'supplier':
                Supplier.objects.create(user=user, name=company_name)
                
            if user.is_superuser:
                messages.success(request, "Admin account registered and activated successfully! You may now log in.")
                return redirect('login')
                
            return render(request, 'registration/registration_pending.html')
    else:
        form = UserRegistrationForm()
        
    return render(request, 'registration/register.html', {'form': form})

@login_required
def submit_volumes(request, tender_id):
    """ONLY FOR AIRLINES"""
    if not hasattr(request.user, 'airline'):
        messages.error(request, "Access Denied: You must be registered as an Airline to submit volumes.")
        return redirect('dashboard')
    
    tender = get_object_or_404(Tender, pk=tender_id)
    qs = VolumeRequirement.objects.filter(tender=tender, airline=request.user.airline)
    
    # Needs to be imported inside the file or at top: from .forms import VolumeFormSet
    from .forms import VolumeFormSet
    
    if request.method == 'POST':
        formset = VolumeFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.tender = tender
                instance.airline = request.user.airline
                instance.save()
            for obj in formset.deleted_objects:
                obj.delete()
            messages.success(request, "Your volume requirements have been saved.")
            return redirect('dashboard')
    else:
        formset = VolumeFormSet(queryset=qs)
        
    return render(request, 'procurement/submit_volumes.html', {
        'tender': tender,
        'formset': formset
    })

@login_required
def submit_bids(request, tender_id):
    """ONLY FOR SUPPLIERS"""
    if not hasattr(request.user, 'supplier'):
        messages.error(request, "Access Denied: Only registered Suppliers can submit bids.")
        return redirect('dashboard')
    
    supplier = request.user.supplier
    if not supplier.is_approved_to_bid():
        messages.error(request, "Access Denied: You must submit all required verification documents and be approved by an administrator to place bids.")
        return redirect('supplier_documents')
    
    tender = get_object_or_404(Tender, pk=tender_id)
    
    if not tender.volumes_released and not request.user.is_superuser:
        messages.warning(request, "Bidding Locked: The Administrator has not yet finalized and released the fuel volume requirements for this tender.")
        return redirect('dashboard')
    
    from django.utils import timezone
    today = timezone.localdate()
    
    if today > tender.end_date:
        messages.error(request, f"The submission deadline ({tender.end_date}) for this tender has passed.")
        return redirect('dashboard')
    
    if tender.current_round < 1 or tender.current_round > 3:
        messages.error(request, f"Bidding is not currently open for this tender. Current round: {tender.current_round}")
        return redirect('dashboard')
        
    volume_requests = VolumeRequirement.objects.filter(tender=tender).select_related('airport', 'airline', 'uom').order_by('airport__name', 'airline__name')
    
    if request.method == 'POST':
        for req in volume_requests:
            diff = request.POST.get(f'diff_{req.id}')
            if diff and diff.strip():
                tax_names = request.POST.getlist(f'tax_name_{req.id}')
                tax_rates = request.POST.getlist(f'tax_rate_{req.id}')
                tax_currs = request.POST.getlist(f'tax_curr_{req.id}')
                tax_uoms = request.POST.getlist(f'tax_uom_{req.id}')
                tax_methods = request.POST.getlist(f'tax_method_{req.id}')
                tax_cats = request.POST.getlist(f'tax_cat_{req.id}')
                
                taxes = []
                for i in range(len(tax_names)):
                    if tax_names[i].strip():
                        taxes.append({
                            'name': tax_names[i],
                            'rate': float(tax_rates[i] or 0),
                            'currency': tax_currs[i] if i < len(tax_currs) else 'USD',
                            'uom': tax_uoms[i] if i < len(tax_uoms) else 'USG',
                            'method': tax_methods[i] if i < len(tax_methods) else 'UNIT',
                            'category': tax_cats[i] if i < len(tax_cats) else 'MANDATORY'
                        })
                
                Bid.objects.update_or_create(
                    tender=tender,
                    airport=req.airport,
                    airline=req.airline,
                    supplier=request.user.supplier,
                    round_number=tender.current_round,
                    defaults={
                        'price_basis': request.POST.get(f'basis_name_{req.id}', 'Platts'),
                        'reference_price_amount': request.POST.get(f'basis_amt_{req.id}') or 0,
                        'differential_price': diff,
                        'currency': Currency.objects.get(code=request.POST.get(f'curr_{req.id}')),
                        'uom': UnitOfMeasure.objects.get(code=request.POST.get(f'uom_{req.id}')),
                        'volume_percentage_offered': request.POST.get(f'vol_perc_{req.id}', 100),
                        'invoicing_frequency': request.POST.get(f'inv_freq_{req.id}', 30),
                        'credit_period': request.POST.get(f'credit_days_{req.id}', 30),
                        'tax_breakdown': json.dumps(taxes)
                    }
                )
        messages.success(request, "Your formal bids have been securely submitted.")
        return redirect('dashboard')

    existing_bids = Bid.objects.filter(tender=tender, supplier=request.user.supplier, round_number__lte=tender.current_round).order_by('airport', 'airline', 'round_number')
    bid_map = {f"{b.airport.id}_{b.airline.id}": {"bid": b, "taxes": json.loads(b.tax_breakdown) if b.tax_breakdown else []} for b in existing_bids}

    from django.db.models import Sum
    airport_totals = VolumeRequirement.objects.filter(tender=tender).values('airport_id').annotate(total_usg=Sum('volume_usg'))
    airport_totals_map = {item['airport_id']: float(item['total_usg'] or 0) for item in airport_totals}

    return render(request, 'procurement/bidForm.html', {
        'tender': tender,
        'volume_requests': volume_requests,
        'bid_map': bid_map,
        'currencies': Currency.objects.all(),
        'uoms': UnitOfMeasure.objects.all(),
        'airport_totals_map': airport_totals_map,
    })

@login_required
def analysis_dashboard(request, tender_id):
    """ONLY FOR AFRAA ADMINS (Superusers)"""
    if not request.user.is_superuser:
        messages.error(request, "Access Denied: Admin privileges required.")
        return redirect('dashboard')
    
    tender = get_object_or_404(Tender, pk=tender_id)

    # Load currencies and units for the selector controls
    currencies = Currency.objects.all()
    uoms = UnitOfMeasure.objects.all()

    # Get requested target standardization parameters (optional)
    target_curr = request.GET.get('target_curr') or (currencies.first().code if currencies.exists() else None)
    target_uom = request.GET.get('target_uom') or (uoms.first().code if uoms.exists() else None)

    # Build analysis matrix per airport using available bids and volume requirements
    # Group volume requirements by airport
    vols = VolumeRequirement.objects.filter(tender=tender).select_related('airport', 'airline', 'uom')
    airport_map = defaultdict(list)
    for v in vols:
        airport_map[v.airport.id].append(v)

    matrix = []
    # Preload target unit and currency objects if provided
    target_uom_obj = None
    target_curr_code = target_curr
    if target_uom:
        try:
            target_uom_obj = UnitOfMeasure.objects.get(code=target_uom)
        except UnitOfMeasure.DoesNotExist:
            target_uom_obj = None

    for airport_id, vol_list in airport_map.items():
        demand = vol_list[0]
        airport = demand.airport

        bids_qs = Bid.objects.filter(tender=tender, airport=airport, round_number__lte=tender.current_round).select_related('supplier', 'currency', 'uom').order_by('supplier', 'airline', 'round_number')
        
        latest_bids = {}
        for b in bids_qs:
            latest_bids[f"{b.supplier.id}_{b.airline.id}"] = b

        bids_data = []
        for b in latest_bids.values():
            bid_data = BidAnalyzer.analyze_bid(b, target_curr_code, target_uom_obj, tender, vol_list)
            bids_data.append(bid_data)

        # sort bids by total_landed_cost
        bids_data.sort(key=lambda x: x['total_landed_cost'])
        if bids_data:
            best = Decimal(str(bids_data[0]['total_landed_cost']))
            for bid in bids_data:
                try:
                    cost = Decimal(str(bid['total_landed_cost']))
                    gap = ((cost - best) / abs(best) * Decimal(100)) if best != 0 else Decimal(0)
                except Exception:
                    gap = Decimal(0)
                bid['gap_percent'] = float(gap)

        matrix.append({'demand': demand, 'bids': bids_data})

    return render(request, 'procurement/analysis.html', {
        'tender': tender,
        'currencies': currencies,
        'uoms': uoms,
        'matrix': matrix,
        'target_curr': target_curr,
        'target_uom': target_uom,
    })

@login_required
def supplier_analysis_dashboard(request, tender_id):
    """ONLY FOR SUPPLIERS: Live Ranking Dashboard"""
    if not hasattr(request.user, 'supplier'):
        messages.error(request, "Access Denied: Only registered Suppliers can view this dashboard.")
        return redirect('dashboard')
    
    tender = get_object_or_404(Tender, pk=tender_id)
    supplier_name = str(request.user.supplier)

    currencies = Currency.objects.all()
    uoms = UnitOfMeasure.objects.all()
    target_curr = request.GET.get('target_curr') or (currencies.first().code if currencies.exists() else None)
    target_uom = request.GET.get('target_uom') or (uoms.first().code if uoms.exists() else None)

    target_uom_obj = None
    target_curr_code = target_curr
    if target_uom:
        try:
            target_uom_obj = UnitOfMeasure.objects.get(code=target_uom)
        except UnitOfMeasure.DoesNotExist:
            pass

    hide_rankings = not (tender.show_live_ranking or tender.is_past_deadline)

    vols = VolumeRequirement.objects.filter(tender=tender).select_related('airport', 'airline', 'uom')
    airport_map = defaultdict(list)
    for v in vols:
        airport_map[v.airport.id].append(v)

    dashboard_data = []

    for airport_id, vol_list in airport_map.items():
        demand = vol_list[0]
        airport = demand.airport
        
        bids_qs = Bid.objects.filter(tender=tender, airport=airport, round_number__lte=tender.current_round).select_related('supplier', 'currency', 'uom').order_by('supplier', 'airline', 'round_number')
        
        latest_bids = {}
        for b in bids_qs:
            latest_bids[f"{b.supplier.id}_{b.airline.id}"] = b
            
        bids_data = []
        user_bid_exists = False
        
        for b in latest_bids.values():
            if str(b.supplier) == supplier_name:
                user_bid_exists = True
            bid_data = BidAnalyzer.analyze_bid(b, target_curr_code, target_uom_obj, tender, vol_list)
            # Add airline info for clarity in supplier's own dashboard if they bid uniquely
            bid_data['airline'] = b.airline.name if b.airline else 'Unknown Airline'
            bids_data.append(bid_data)
            
        if not user_bid_exists:
            continue
            
        bids_data.sort(key=lambda x: x['total_landed_cost'])
        
        total_bidders = len(bids_data)
        
        if total_bidders > 0:
            best_cost = Decimal(str(bids_data[0]['total_landed_cost']))
            second_best_cost = Decimal(str(bids_data[1]['total_landed_cost'])) if total_bidders > 1 else None
            
            for idx, bid in enumerate(bids_data):
                cost = Decimal(str(bid['total_landed_cost']))
                if idx == 0:
                    if second_best_cost is not None and second_best_cost != 0:
                        # Negative gap meaning cost is cheaper than second best
                        gap = ((cost - second_best_cost) / abs(second_best_cost) * Decimal(100))
                    else:
                        gap = Decimal(0)
                    is_leading = True
                else:
                    if best_cost != 0:
                        gap = ((cost - best_cost) / abs(best_cost) * Decimal(100))
                    else:
                        gap = Decimal(0)
                    is_leading = False
                
                bid['gap_percent'] = float(gap)
                bid['rank'] = idx + 1
                bid['is_leading'] = is_leading
                
                if bid['supplier'] == supplier_name:
                    dashboard_data.append({
                        'airport': airport,
                        'demand': demand,
                        'result': bid,
                        'total_bidders': total_bidders
                    })

    dashboard_data.sort(key=lambda x: x['airport'].name)

    return render(request, 'procurement/supplier_analysis.html', {
        'tender': tender,
        'currencies': currencies,
        'uoms': uoms,
        'target_curr': target_curr,
        'target_uom': target_uom,
        'dashboard_data': dashboard_data,
        'hide_rankings': hide_rankings
    })

@login_required
def airline_analysis_dashboard(request, tender_id):
    """ONLY FOR AIRLINES: Live Ranking Dashboard for their requests"""
    if not hasattr(request.user, 'airline'):
        messages.error(request, "Access Denied: Only registered Airlines can view this dashboard.")
        return redirect('dashboard')
    
    tender = get_object_or_404(Tender, pk=tender_id)
    airline = request.user.airline

    currencies = Currency.objects.all()
    uoms = UnitOfMeasure.objects.all()
    target_curr = request.GET.get('target_curr') or (currencies.first().code if currencies.exists() else None)
    target_uom = request.GET.get('target_uom') or (uoms.first().code if uoms.exists() else None)

    target_uom_obj = None
    target_curr_code = target_curr
    if target_uom:
        try:
            target_uom_obj = UnitOfMeasure.objects.get(code=target_uom)
        except UnitOfMeasure.DoesNotExist:
            pass

    hide_rankings = not (tender.show_live_ranking or tender.is_past_deadline)

    # Filter only for this airline's requirements
    vols = VolumeRequirement.objects.filter(tender=tender, airline=airline).select_related('airport', 'airline', 'uom')
    airport_map = defaultdict(list)
    for v in vols:
        airport_map[v.airport.id].append(v)

    dashboard_data = []

    for airport_id, vol_list in airport_map.items():
        demand = vol_list[0]
        airport = demand.airport
        
        # Only bids for this airline
        bids_qs = Bid.objects.filter(tender=tender, airport=airport, airline=airline, round_number__lte=tender.current_round).select_related('supplier', 'currency', 'uom').order_by('supplier', 'round_number')
        
        latest_bids = {}
        for b in bids_qs:
            latest_bids[b.supplier.id] = b
            
        bids_data = []
        for b in latest_bids.values():
            bid_data = BidAnalyzer.analyze_bid(b, target_curr_code, target_uom_obj, tender, vol_list)
            bids_data.append(bid_data)
            
        bids_data.sort(key=lambda x: x['total_landed_cost'])
        
        total_bidders = len(bids_data)
        
        if total_bidders > 0:
            best_cost = Decimal(str(bids_data[0]['total_landed_cost']))
            
            for idx, bid in enumerate(bids_data):
                cost = Decimal(str(bid['total_landed_cost']))
                if idx == 0:
                    gap = Decimal(0)
                    is_leading = True
                else:
                    if best_cost != 0:
                        gap = ((cost - best_cost) / abs(best_cost) * Decimal(100))
                    else:
                        gap = Decimal(0)
                    is_leading = False
                
                bid['gap_percent'] = float(gap)
                bid['rank'] = idx + 1
                bid['is_leading'] = is_leading
                
            dashboard_data.append({
                'airport': airport,
                'demand': demand,
                'bids': bids_data,
                'total_bidders': total_bidders
            })

    dashboard_data.sort(key=lambda x: x['airport'].name)

    return render(request, 'procurement/airline_analysis.html', {
        'tender': tender,
        'currencies': currencies,
        'uoms': uoms,
        'target_curr': target_curr,
        'target_uom': target_uom,
        'dashboard_data': dashboard_data,
        'hide_rankings': hide_rankings
    })

@login_required
def toggle_live_ranking(request, tender_id):
    """ONLY FOR AFRAA ADMINS: Toggle the visibility of live rankings for a tender"""
    if not request.user.is_superuser:
        messages.error(request, "Access Denied: Admin privileges required.")
        return redirect('dashboard')
    
    tender = get_object_or_404(Tender, pk=tender_id)
    tender.show_live_ranking = not tender.show_live_ranking
    tender.save()
    
    status = "visible continuously" if tender.show_live_ranking else "hidden until round closes"
    messages.success(request, f"Live ranking for {tender.title} is now {status}.")
    return redirect('analysis_dashboard', tender_id=tender.id)

@login_required
def reports_insights(request, tender_id):
    """ONLY FOR AFRAA ADMINS: Generate detailed reports and insights with filters"""
    if not request.user.is_superuser:
        messages.error(request, "Access Denied: Admin privileges required.")
        return redirect('dashboard')
        
    tender = get_object_or_404(Tender, pk=tender_id)
    
    # 1. Fetch filter options
    suppliers = Supplier.objects.filter(bid__tender=tender).distinct()
    airports = Airport.objects.filter(volumerequirement__tender=tender).distinct()
    airlines = Airline.objects.filter(volumerequirement__tender=tender).distinct()
    rounds = [1, 2, 3]
    
    # 2. Get active filter params
    f_supplier = request.GET.get('supplier')
    f_airport = request.GET.get('airport')
    f_airline = request.GET.get('airline')
    f_round = request.GET.get('round')
    
    # Standard standardization targets
    currencies = Currency.objects.all()
    uoms = UnitOfMeasure.objects.all()
    target_curr = request.GET.get('target_curr') or (currencies.first().code if currencies.exists() else 'USD')
    target_uom = request.GET.get('target_uom') or (uoms.first().code if uoms.exists() else 'USG')
    
    target_uom_obj = None
    if target_uom:
        try:
            target_uom_obj = UnitOfMeasure.objects.get(code=target_uom)
        except UnitOfMeasure.DoesNotExist:
            pass
            
    # 3. Query Bids and Volume Requirements with Filters
    bids_qs = Bid.objects.filter(tender=tender).select_related('supplier', 'airport', 'airline', 'currency', 'uom')
    vols_qs = VolumeRequirement.objects.filter(tender=tender).select_related('airport', 'airline', 'uom')
    
    if f_supplier:
        bids_qs = bids_qs.filter(supplier_id=f_supplier)
    if f_airport:
        bids_qs = bids_qs.filter(airport_id=f_airport)
        vols_qs = vols_qs.filter(airport_id=f_airport)
    if f_airline:
        bids_qs = bids_qs.filter(airline_id=f_airline)
        vols_qs = vols_qs.filter(airline_id=f_airline)
    if f_round:
        bids_qs = bids_qs.filter(round_number=f_round)
        
    # 4. Analyze each bid to get standard pricing/landed cost
    analyzed_bids = []
    total_volume_usg = sum(v.volume_usg for v in vols_qs)
    
    for b in bids_qs:
        # Find matching volume requirements for this bid (specific to airport and airline)
        b_vols = [v for v in vols_qs if v.airport_id == b.airport_id and v.airline_id == b.airline_id]
        if not b_vols:
            # Fallback to general airport volumes if no airline-specific matches exist in filtered set
            b_vols = list(VolumeRequirement.objects.filter(tender=tender, airport=b.airport))
            
        data = BidAnalyzer.analyze_bid(b, target_curr, target_uom_obj, tender, b_vols)
        data['bid_obj'] = b
        analyzed_bids.append(data)
        
    # Sort analyzed bids by total landed cost (lowest first)
    analyzed_bids.sort(key=lambda x: x['total_landed_cost'])
    
    # 5. Compute insights and aggregates
    bid_count = len(analyzed_bids)
    avg_differential = 0
    avg_landed_cost = 0
    cheapest_bid = None
    most_expensive_bid = None
    
    if bid_count > 0:
        avg_differential = sum(x['standardized_differential'] for x in analyzed_bids) / bid_count
        avg_landed_cost = sum(x['total_landed_cost'] for x in analyzed_bids) / bid_count
        cheapest_bid = analyzed_bids[0]
        most_expensive_bid = analyzed_bids[-1]
        
    # Dynamic natural language insights list
    insights_list = []
    
    if bid_count > 0:
        insights_list.append(
            f"A total of <strong>{bid_count} bids</strong> were evaluated across the selected filters. "
            f"The average bidded differential is <strong>{avg_differential:,.4f} {target_curr}/{target_uom}</strong>."
        )
        if cheapest_bid:
            insights_list.append(
                f"The most competitive bid is submitted by <strong>{cheapest_bid['supplier']}</strong> for "
                f"<strong>{cheapest_bid['bid_obj'].airline.name if cheapest_bid['bid_obj'].airline else 'all airlines'}</strong> "
                f"at <strong>{cheapest_bid['bid_obj'].airport.display_code}</strong>, offering a Net Landed Cost of "
                f"<strong>{cheapest_bid['total_landed_cost']:,.4f} {target_curr}/{target_uom}</strong> "
                f"(differential of {cheapest_bid['standardized_differential']:,.4f})."
            )
        
        # Competitiveness by supplier (who is cheapest most often?)
        supplier_win_counts = defaultdict(int)
        # Group analyzed bids by airport and airline, find the cheapest supplier for each unique demand
        demand_groups = defaultdict(list)
        for ab in analyzed_bids:
            key = f"{ab['bid_obj'].airport_id}_{ab['bid_obj'].airline_id}"
            demand_groups[key].append(ab)
            
        for key, group in demand_groups.items():
            group.sort(key=lambda x: x['total_landed_cost'])
            cheapest_in_group = group[0]
            supplier_win_counts[cheapest_in_group['supplier']] += 1
            
        if supplier_win_counts:
            top_supplier = max(supplier_win_counts, key=supplier_win_counts.get)
            insights_list.append(
                f"Supplier <strong>{top_supplier}</strong> is the most competitive at this location/subset, "
                f"leading in <strong>{supplier_win_counts[top_supplier]} specific airline volume allocation(s)</strong>."
            )
    else:
        insights_list.append("No bids match the currently applied filters. Try relaxing your search criteria.")
        
    # Active round insight
    insights_list.append(
        f"This tender is currently in <strong>Round {tender.current_round}</strong>. "
        f"Deadlines: Round 1 (<strong>{tender.round1_deadline or 'N/A'}</strong>), "
        f"Round 2 (<strong>{tender.round2_deadline or 'N/A'}</strong>), "
        f"Round 3 (<strong>{tender.round3_deadline or 'N/A'}</strong>)."
    )
    
    # 6. Render
    return render(request, 'procurement/reports_insights.html', {
        'tender': tender,
        'suppliers': suppliers,
        'airports': airports,
        'airlines': airlines,
        'rounds': rounds,
        'currencies': currencies,
        'uoms': uoms,
        'target_curr': target_curr,
        'target_uom': target_uom,
        'f_supplier': f_supplier,
        'f_airport': f_airport,
        'f_airline': f_airline,
        'f_round': f_round,
        'analyzed_bids': analyzed_bids,
        'total_volume_usg': total_volume_usg,
        'bid_count': bid_count,
        'avg_differential': avg_differential,
        'avg_landed_cost': avg_landed_cost,
        'cheapest_bid': cheapest_bid,
        'most_expensive_bid': most_expensive_bid,
        'insights': insights_list
    })


@login_required
def supplier_documents(request):
    if not hasattr(request.user, 'supplier'):
        messages.error(request, "Access Denied: Only registered Suppliers can manage verification documents.")
        return redirect('dashboard')
        
    supplier = request.user.supplier
    documents = supplier.documents.all()
    
    if request.method == 'POST':
        form = SupplierDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc_type = form.cleaned_data['document_type']
            file = form.cleaned_data['file']
            
            # Find existing document of this type, if any, to update it
            doc, created = SupplierDocument.objects.get_or_create(
                supplier=supplier,
                document_type=doc_type
            )
            doc.file = file
            doc.status = 'PENDING'
            doc.rejection_reason = ''
            doc.save()
            
            messages.success(request, f"Document '{doc.get_document_type_display()}' uploaded successfully. It is now pending review.")
            return redirect('supplier_documents')
    else:
        form = SupplierDocumentForm()
        
    uploaded_types = [doc.document_type for doc in documents]
    required_types = ['business_registration', 'insurance']
    missing_docs = [t for t in required_types if t not in uploaded_types]
    
    # Map friendly status names
    status_map = dict(SupplierDocument.STATUS_CHOICES)
    
    return render(request, 'procurement/supplier_documents.html', {
        'supplier': supplier,
        'documents': documents,
        'form': form,
        'missing_docs': missing_docs,
        'status_map': status_map,
    })


@login_required
def admin_console(request):
    """ONLY FOR AFRAA ADMINS (Superusers): Consolidated Settings Dashboard"""
    if not request.user.is_superuser:
        messages.error(request, "Access Denied: Admin privileges required.")
        return redirect('dashboard')

    from django.contrib.auth.models import User
    from procurement.models import Airport, Airline, Supplier, Currency, GlobalConfig, Tender, SupplierDocument

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'release_volumes':
            tender_id = request.POST.get('tender_id')
            tender = get_object_or_404(Tender, pk=tender_id)
            tender.volumes_released = True
            tender.save()
            messages.success(request, f"Fuel volumes for tender '{tender.title}' have been successfully released to suppliers.")

        elif action == 'approve_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, pk=user_id)
            user.is_active = True
            user.save()
            messages.success(request, f"User account '{user.username}' has been approved and activated.")

        elif action == 'reject_user':
            user_id = request.POST.get('user_id')
            user = get_object_or_404(User, pk=user_id)
            username = user.username
            user.delete()
            messages.success(request, f"User account '{username}' registration request was rejected and deleted.")

        elif action == 'approve_doc':
            doc_id = request.POST.get('doc_id')
            doc = get_object_or_404(SupplierDocument, pk=doc_id)
            doc.status = 'APPROVED'
            doc.rejection_reason = ''
            doc.save()
            messages.success(request, f"Supplier document '{doc.get_document_type_display()}' for '{doc.supplier.name}' was approved.")

        elif action == 'reject_doc':
            doc_id = request.POST.get('doc_id')
            reason = request.POST.get('rejection_reason', '').strip()
            doc = get_object_or_404(SupplierDocument, pk=doc_id)
            doc.status = 'REJECTED'
            doc.rejection_reason = reason or "Incomplete or invalid documentation."
            doc.save()
            messages.warning(request, f"Supplier document '{doc.get_document_type_display()}' for '{doc.supplier.name}' was rejected.")

        elif action == 'add_airport':
            icao = request.POST.get('icao_code', '').strip().upper()
            iata = request.POST.get('iata_code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            country = request.POST.get('country', '').strip()

            if not icao or not name or not country:
                messages.error(request, "Failed to Add Airport: ICAO code, name, and country are required.")
            elif Airport.objects.filter(icao_code=icao).exists():
                messages.error(request, f"Failed to Add Airport: An airport with ICAO code '{icao}' already exists.")
            else:
                Airport.objects.create(icao_code=icao, iata_code=iata, name=name, country=country)
                messages.success(request, f"Airport '{name}' ({icao}) has been added to the system.")

        elif action == 'add_currency':
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            rate = request.POST.get('exchange_rate_to_usd', '').strip()
            symbol = request.POST.get('symbol', '').strip() or '$'

            if not code or not name or not rate:
                messages.error(request, "Failed to Add Currency: Code, name, and exchange rate are required.")
            elif Currency.objects.filter(code=code).exists():
                messages.error(request, f"Failed to Add Currency: Currency '{code}' already exists.")
            else:
                try:
                    Currency.objects.create(code=code, name=name, exchange_rate_to_usd=Decimal(rate), symbol=symbol)
                    messages.success(request, f"Currency '{code}' ({name}) has been added.")
                except Exception as e:
                    messages.error(request, f"Error adding currency: {str(e)}")

        elif action == 'update_currency_rate':
            currency_id = request.POST.get('currency_id')
            rate = request.POST.get('exchange_rate_to_usd', '').strip()
            if not currency_id or not rate:
                messages.error(request, "Failed to Update Exchange Rate: Currency selection and rate are required.")
            else:
                try:
                    currency = Currency.objects.get(pk=currency_id)
                    currency.exchange_rate_to_usd = Decimal(rate)
                    currency.save()
                    messages.success(request, f"Exchange rate for '{currency.code}' updated to {rate} USD.")
                except Exception as e:
                    messages.error(request, f"Error updating rate: {str(e)}")

        elif action == 'update_credit_apr':
            rate = request.POST.get('cost_of_credit_apr', '').strip()
            if not rate:
                messages.error(request, "Failed to Update APR: Value is required.")
            else:
                try:
                    GlobalConfig.objects.update_or_create(
                        key='cost_of_credit_apr',
                        defaults={'value': Decimal(rate)}
                    )
                    messages.success(request, f"Global cost of credit APR has been updated to {rate}%.")
                except Exception as e:
                    messages.error(request, f"Error updating APR: {str(e)}")

        elif action == 'add_airline':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            company_name = request.POST.get('company_name', '').strip()

            if not username or not email or not password or not company_name:
                messages.error(request, "Failed to Create Airline: All fields are required.")
            elif User.objects.filter(username=username).exists():
                messages.error(request, f"Failed to Create Airline: Username '{username}' is already taken.")
            else:
                try:
                    user = User.objects.create_user(username=username, email=email, password=password, is_active=True)
                    Airline.objects.create(user=user, name=company_name)
                    messages.success(request, f"Airline profile and user account for '{company_name}' created successfully.")
                except Exception as e:
                    messages.error(request, f"Error creating airline: {str(e)}")

        elif action == 'add_supplier':
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            company_name = request.POST.get('company_name', '').strip()

            if not username or not email or not password or not company_name:
                messages.error(request, "Failed to Create Supplier: All fields are required.")
            elif User.objects.filter(username=username).exists():
                messages.error(request, f"Failed to Create Supplier: Username '{username}' is already taken.")
            else:
                try:
                    user = User.objects.create_user(username=username, email=email, password=password, is_active=True)
                    Supplier.objects.create(user=user, name=company_name)
                    messages.success(request, f"Supplier profile and user account for '{company_name}' created successfully.")
                except Exception as e:
                    messages.error(request, f"Error creating supplier: {str(e)}")

        return redirect('admin_console')

    # GET Request: Fetch data
    tenders = Tender.objects.all().order_by('-start_date')
    pending_users = User.objects.filter(is_active=False).select_related('airline', 'supplier')
    pending_documents = SupplierDocument.objects.filter(status='PENDING').select_related('supplier')
    approved_documents = SupplierDocument.objects.filter(status='APPROVED').select_related('supplier')
    rejected_documents = SupplierDocument.objects.filter(status='REJECTED').select_related('supplier')
    airports = Airport.objects.all().order_by('iata_code', 'icao_code')
    currencies = Currency.objects.all().order_by('code')
    airlines = Airline.objects.all().order_by('name')
    suppliers = Supplier.objects.all().order_by('name')

    try:
        credit_apr_obj = GlobalConfig.objects.get(key='cost_of_credit_apr')
        credit_apr = credit_apr_obj.value
    except GlobalConfig.DoesNotExist:
        credit_apr = Decimal('12.00')

    # Calculate volume requirement submission status for each tender
    tender_release_info = []
    total_registered_airlines = Airline.objects.count()

    for t in tenders:
        # Number of unique airlines that submitted volumes
        submitted_count = VolumeRequirement.objects.filter(tender=t, is_submitted=True).values_list('airline_id', flat=True).distinct().count()
        # Find which airlines haven't submitted yet
        submitted_ids = set(VolumeRequirement.objects.filter(tender=t, is_submitted=True).values_list('airline_id', flat=True).distinct())
        pending_airlines_list = [a.name for a in airlines if a.id not in submitted_ids]

        tender_release_info.append({
            'tender': t,
            'submitted_airlines_count': submitted_count,
            'total_airlines': total_registered_airlines,
            'pending_airlines': pending_airlines_list,
            'volumes_released': t.volumes_released
        })

    return render(request, 'procurement/admin_console.html', {
        'tenders_info': tender_release_info,
        'pending_users': pending_users,
        'pending_documents': pending_documents,
        'approved_documents': approved_documents,
        'rejected_documents': rejected_documents,
        'airports': airports,
        'currencies': currencies,
        'airlines': airlines,
        'suppliers': suppliers,
        'credit_apr': credit_apr,
    })
from django.db import models
from django.contrib.auth.models import User
import json
from decimal import Decimal

# --- Configuration Models ---

class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True) # e.g., USD, KES, EUR
    name = models.CharField(max_length=50)
    exchange_rate_to_usd = models.DecimalField(max_digits=15, decimal_places=6, default=1.0)
    symbol = models.CharField(max_length=5, default='$')

    def __str__(self):
        return self.code

class UnitOfMeasure(models.Model):
    code = models.CharField(max_length=10, unique=True) # e.g., USG, Litre, MT
    conversion_to_usg = models.DecimalField(max_digits=15, decimal_places=6) # How many USG in 1 unit?

    def __str__(self):
        return self.code

class GlobalConfig(models.Model):
    key = models.CharField(max_length=50, primary_key=True) # e.g., 'cost_of_credit_rate'
    value = models.DecimalField(max_digits=10, decimal_places=4) # e.g., 0.12 for 12%

    def __str__(self):
        return self.key


class ExchangeRate(models.Model):
    currency = models.CharField(max_length=10)
    target_currency = models.CharField(max_length=10)
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    source = models.CharField(max_length=200, blank=True, null=True)
    retrieved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.currency}->{self.target_currency} {self.rate}"

# --- Core Business Models ---

class Airport(models.Model):
    icao_code = models.CharField(max_length=4, unique=True)
    iata_code = models.CharField(max_length=3, blank=True)
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=100)

    def __str__(self):
        if self.iata_code:
            return f"{self.iata_code} ({self.icao_code})"
        return self.icao_code

    @property
    def display_code(self):
        return self.iata_code or self.icao_code

class TaxTemplate(models.Model):
    CALC_CHOICES = [('UNIT', 'Per Unit'), ('UPTAKE', 'Per Uptake')]
    TYPE_CHOICES = [('MANDATORY', 'Mandatory'), ('CONDITIONAL', 'Conditional')]
    
    name = models.CharField(max_length=100)
    airport = models.ForeignKey(Airport, on_delete=models.CASCADE, related_name='taxes')
    calculation_method = models.CharField(max_length=10, choices=CALC_CHOICES)
    category = models.CharField(max_length=15, choices=TYPE_CHOICES)
    rate = models.DecimalField(max_digits=12, decimal_places=4)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)

class Tender(models.Model):
    title = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    
    # 3-Round Bidding Deadlines
    timezone = models.CharField(max_length=50, default='UTC', help_text="Timezone for the deadlines, e.g., 'UTC', 'Africa/Nairobi', 'Europe/London'")
    round1_deadline = models.DateTimeField(null=True, blank=True)
    round2_deadline = models.DateTimeField(null=True, blank=True)
    round3_deadline = models.DateTimeField(null=True, blank=True)
    
    current_round = models.IntegerField(default=0)
    cost_of_credit_rate = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    show_live_ranking = models.BooleanField(default=True, help_text="If True, rankings are shown continuously. If False, rankings are hidden until the round closes.")

    @property
    def current_round_deadline(self):
        if self.current_round == 1:
            return self.round1_deadline
        elif self.current_round == 2:
            return self.round2_deadline
        elif self.current_round == 3:
            return self.round3_deadline
        return None

    @property
    def is_past_deadline(self):
        from django.utils import timezone as django_timezone
        deadline = self.current_round_deadline
        if deadline:
            return django_timezone.now() > deadline
        # Fallback to general end_date if no specific round deadline is set
        return django_timezone.localdate() > self.end_date

    def __str__(self):
        return self.title

class Airline(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Supplier(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    def has_uploaded_all_required_docs(self):
        uploaded_types = self.documents.values_list('document_type', flat=True)
        return 'business_registration' in uploaded_types and 'insurance' in uploaded_types

    def is_approved_to_bid(self):
        required_types = ['business_registration', 'insurance']
        approved_types = self.documents.filter(status='APPROVED').values_list('document_type', flat=True)
        return all(t in approved_types for t in required_types)


class VolumeRequirement(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE)
    airline = models.ForeignKey(Airline, on_delete=models.CASCADE)
    airport = models.ForeignKey(Airport, on_delete=models.CASCADE)
    
    # Original values from the Airline's submission form
    volume_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE, null=True)
    
    # Normalized value calculated automatically in views.py for the standardization engine
    volume_usg = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    uptakes_per_year = models.IntegerField(default=365)
    is_submitted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.airport.icao_code} - {self.airline.name}"

class Bid(models.Model):
    tender = models.ForeignKey(Tender, on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE)
    airport = models.ForeignKey(Airport, on_delete=models.CASCADE)
    airline = models.ForeignKey(Airline, on_delete=models.CASCADE, null=True)
    differential_price = models.DecimalField(max_digits=12, decimal_places=4)
    reference_price_amount = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    price_basis = models.CharField(max_length=100, default="CIF NWE HIGH")
    taxes_total = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    tax_breakdown = models.TextField(blank=True, null=True) # Stores JSON list of multiple taxes
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, default=1.0)
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE)
    invoicing_frequency = models.IntegerField(default=30)
    credit_period = models.IntegerField(default=30)
    payment_terms = models.CharField(max_length=200, blank=True)
    round_number = models.IntegerField(default=1)
    volume_percentage_offered = models.DecimalField(max_digits=5, decimal_places=2, default=100)

    def get_parsed_taxes(self):
        """Returns a tuple of (tax_items_list, total_fees_decimal) parsed from tax_breakdown."""
        fees = Decimal(0)
        tax_items = []
        if not self.tax_breakdown:
            return tax_items, Decimal(self.taxes_total or 0)

        try:
            parsed = json.loads(self.tax_breakdown) if isinstance(self.tax_breakdown, str) else self.tax_breakdown
        except Exception:
            parsed = self.tax_breakdown

        if isinstance(parsed, list):
            for t in parsed:
                if isinstance(t, dict):
                    name = t.get('name')
                    raw_val = t.get('rate')
                    if raw_val is None:
                        raw_val = t.get('amount', 0)
                        
                    try:
                        amt = Decimal(str(raw_val))
                    except Exception:
                        amt = Decimal(0)
                        
                    curr = t.get('currency')
                    uom = t.get('uom', 'USG')
                    method = t.get('method', 'UNIT')
                    cat = t.get('category', 'MANDATORY_INCLUDED')
                    
                    if cat == 'MANDATORY':
                        cat = 'MANDATORY_INCLUDED'
                        
                    tax_items.append({
                        'name': name, 
                        'amount': float(amt), 
                        'currency': curr, 
                        'uom': uom,
                        'method': method,
                        'category': cat
                    })
                    fees += amt
                elif isinstance(t, (list, tuple)):
                    try:
                        name = t[0]
                        amt = Decimal(str(t[1]))
                        curr = t[2] if len(t) > 2 else None
                    except Exception:
                        name = None
                        amt = Decimal(0)
                        curr = None
                    tax_items.append({'name': name, 'amount': float(amt), 'currency': curr, 'uom': 'USG', 'method': 'UNIT', 'category': 'MANDATORY_INCLUDED'})
                    fees += amt
        elif isinstance(parsed, dict):
            for name, val in parsed.items():
                try:
                    amt = Decimal(str(val))
                except Exception:
                    amt = Decimal(0)
                tax_items.append({'name': name, 'amount': float(amt), 'currency': None, 'uom': 'USG', 'method': 'UNIT', 'category': 'MANDATORY_INCLUDED'})
                fees += amt
        elif isinstance(parsed, str):
            parts = [p.strip() for p in parsed.split(',') if p.strip()]
            for p in parts:
                bits = p.split(':')
                try:
                    name = bits[0]
                    amt = Decimal(bits[1]) if len(bits) > 1 else Decimal(0)
                    curr = bits[2] if len(bits) > 2 else None
                except Exception:
                    name = p
                    amt = Decimal(0)
                    curr = None
                tax_items.append({'name': name, 'amount': float(amt), 'currency': curr, 'uom': 'USG', 'method': 'UNIT', 'category': 'MANDATORY_INCLUDED'})
                fees += amt

        # Fallback to legacy
        if not tax_items and self.taxes_total:
            fees = Decimal(self.taxes_total)
            
        return tax_items, fees


class SupplierDocument(models.Model):
    DOCUMENT_TYPES = [
        ('business_registration', 'Business Registration'),
        ('insurance', 'Insurance Certificate'),
        ('other', 'Other Supporting Document'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to='supplier_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    rejection_reason = models.TextField(blank=True, null=True)
    insured_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)


    def __str__(self):
        return f"{self.supplier.name} - {self.get_document_type_display()} ({self.status})"
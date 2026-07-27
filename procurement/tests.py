from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Tender, Currency, UnitOfMeasure, Airport, Airline, Supplier, VolumeRequirement, Bid
from decimal import Decimal


class AnalysisViewTests(TestCase):
	def setUp(self):
		# Create currencies and units
		self.curr = Currency.objects.create(code='USD', name='US Dollar', exchange_rate_to_usd=1, symbol='$')
		self.uom = UnitOfMeasure.objects.create(code='USG', conversion_to_usg=1)

		# Tender
		self.tender = Tender.objects.create(title='T1', start_date='2025-01-01', end_date='2026-12-31')

		# Create users
		self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'adminpass')
		self.supplier_user = User.objects.create_user('supplier', 'sup@example.com', 'suppass')
		self.supplier = Supplier.objects.create(user=self.supplier_user, name='FuelCo')
		from django.core.files.uploadedfile import SimpleUploadedFile
		from .models import SupplierDocument
		SupplierDocument.objects.create(
			supplier=self.supplier,
			document_type='business_registration',
			file=SimpleUploadedFile('reg.pdf', b'content', content_type='application/pdf'),
			status='APPROVED'
		)
		SupplierDocument.objects.create(
			supplier=self.supplier,
			document_type='insurance',
			file=SimpleUploadedFile('ins.pdf', b'content', content_type='application/pdf'),
			status='APPROVED'
		)


		# Airport and airline
		self.airport = Airport.objects.create(icao_code='XXXX', name='Test Airport', country='Testland')
		self.airline_user = User.objects.create_user('airline', 'air@example.com', 'airpass')
		self.airline = Airline.objects.create(user=self.airline_user, name='TestAir')

		# Volume requirement
		self.vol = VolumeRequirement.objects.create(tender=self.tender, airline=self.airline, airport=self.airport, volume_amount=1000, uom=self.uom, volume_usg=1000)

		# Bid
		self.bid = Bid.objects.create(
			tender=self.tender,
			supplier=self.supplier,
			airport=self.airport,
			airline=self.airline,
			differential_price=Decimal('1.50'),
			reference_price_amount=Decimal('100.00'),
			taxes_total=Decimal('5.00'),
			currency=self.curr,
			exchange_rate=Decimal('1'),
			uom=self.uom,
		)

	def test_analysis_view_requires_superuser(self):
		c = Client()
		c.login(username='supplier', password='suppass')
		resp = c.get(f'/tender/{self.tender.id}/analysis/')
		# Non-superuser should be redirected to dashboard
		self.assertIn(resp.status_code, (302, 301))

	def test_analysis_view_shows_matrix_for_admin(self):
		c = Client()
		c.login(username='admin', password='adminpass')
		resp = c.get(f'/tender/{self.tender.id}/analysis/')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Analysis Matrix')
		# Ensure matrix contains bids and tax/fx/weight fields
		content = resp.content.decode('utf-8')
		self.assertTrue('Net Landed Price' in content or 'total_landed_cost' in content)

	def test_volume_formset_rejects_duplicate_airports(self):
		from procurement.forms import VolumeFormSet
		data = {
			'form-TOTAL_FORMS': '2',
			'form-INITIAL_FORMS': '0',
			'form-MIN_NUM_FORMS': '0',
			'form-MAX_NUM_FORMS': '1000',
			'form-0-airport': self.airport.id,
			'form-0-volume_amount': '1500',
			'form-0-uom': self.uom.id,
			'form-1-airport': self.airport.id, # Duplicate!
			'form-1-volume_amount': '2500',
			'form-1-uom': self.uom.id,
		}
		formset = VolumeFormSet(data=data)
		self.assertFalse(formset.is_valid())
		self.assertTrue(any('You can only submit one volume per location' in str(f.errors) for f in formset.forms))

	def test_reports_insights_view_shows_filtered_insights(self):
		c = Client()
		c.login(username='admin', password='adminpass')
		resp = c.get(f'/tender/{self.tender.id}/reports/')
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, 'Reports & Insights Workbench')
		self.assertContains(resp, 'FuelCo')

	def test_custom_currency_conversion_usc_to_usd(self):
		from procurement.services import get_exchange_rate
		# Create USC currency
		usc = Currency.objects.create(code='USC', name='US cents', exchange_rate_to_usd=Decimal('100.000000'), symbol='¢')
		
		# Test USC -> USD exchange rate
		rate_info = get_exchange_rate('USC', 'USD')
		self.assertEqual(rate_info['rate'], Decimal('0.01'))
		self.assertEqual(rate_info['source'], 'local-currency-table')
		
		# Test USD -> USC exchange rate
		rate_info_reverse = get_exchange_rate('USD', 'USC')
		self.assertEqual(rate_info_reverse['rate'], Decimal('100'))
		self.assertEqual(rate_info_reverse['source'], 'local-currency-table')

	def test_volume_formset_ignores_empty_rows(self):
		from procurement.forms import VolumeFormSet
		data = {
			'form-TOTAL_FORMS': '3',
			'form-INITIAL_FORMS': '0',
			'form-MIN_NUM_FORMS': '0',
			'form-MAX_NUM_FORMS': '1000',
			'form-0-airport': self.airport.id,
			'form-0-volume_amount': '1500',
			'form-0-uom': self.uom.id,
			'form-1-airport': '',       # Empty row!
			'form-1-volume_amount': '',  # Empty row!
			'form-1-uom': self.uom.id,
			'form-2-airport': '',       # Another empty row!
			'form-2-volume_amount': '',
			'form-2-uom': self.uom.id,
		}
		formset = VolumeFormSet(data=data)
		self.assertTrue(formset.is_valid())
		forms_to_save = [f for f in formset.forms if f.has_changed() and not formset._should_delete_form(f)]
		self.assertEqual(len(forms_to_save), 1)
		self.assertEqual(forms_to_save[0].cleaned_data['volume_amount'], 1500)

	def test_new_currency_conversion_uses_local_currency_table(self):
		from procurement.services import get_exchange_rate
		# Create a new currency ZAR (1 USD = 18 ZAR)
		zar = Currency.objects.create(code='ZAR', name='South African Rand', exchange_rate_to_usd=Decimal('18.000000'), symbol='R')
		
		# Test ZAR -> USD conversion
		rate_info = get_exchange_rate('ZAR', 'USD')
		self.assertEqual(rate_info['rate'], Decimal('1') / Decimal('18'))
		self.assertEqual(rate_info['source'], 'local-currency-table')
		
		# Test USD -> ZAR conversion
		rate_info_reverse = get_exchange_rate('USD', 'ZAR')
		self.assertEqual(rate_info_reverse['rate'], Decimal('18'))
		self.assertEqual(rate_info_reverse['source'], 'local-currency-table')

	def test_supplier_bid_form_features(self):
		self.tender.current_round = 1
		self.tender.save()
		# Create a supplier user
		c = Client()
		c.login(username='supplier', password='suppass')
		
		# GET the bidForm page
		resp = c.get(f'/tender/{self.tender.id}/bids/')
		self.assertEqual(resp.status_code, 200)
		
		# Check context variables
		self.assertIn('airport_totals_map', resp.context)
		self.assertEqual(resp.context['airport_totals_map'][self.airport.id], 1000.0)
		
		# Check template elements
		content = resp.content.decode('utf-8')
		self.assertIn('Sort Locations By:', content)
		self.assertIn('Total Volume:', content)
		self.assertIn('Capacity Offered (%)', content)
		self.assertIn('js-vol-perc-input', content)

	def test_volume_form_dropdown_ordering(self):
		from procurement.forms import VolumeForm
		# Create multiple airports
		Airport.objects.create(icao_code='EGLL', iata_code='LHR', name='London Heathrow', country='UK')
		Airport.objects.create(icao_code='HAAB', iata_code='ADD', name='Addis Ababa', country='Ethiopia')
		Airport.objects.create(icao_code='FAOR', iata_code='JNB', name='Johannesburg', country='South Africa')
		
		form = VolumeForm()
		airports_queryset = form.fields['airport'].queryset
		# Check if the ordering is alphabetically by iata_code
		codes = [a.iata_code for a in airports_queryset if a.iata_code]
		self.assertEqual(codes, sorted(codes))


class SupplierVerificationTests(TestCase):
    def setUp(self):
        self.curr = Currency.objects.create(code='USD', name='US Dollar', exchange_rate_to_usd=1, symbol='$')
        self.uom = UnitOfMeasure.objects.create(code='USG', conversion_to_usg=1)
        self.tender = Tender.objects.create(title='T1', start_date='2025-01-01', end_date='2026-12-31', current_round=1)
        
        self.supplier_user = User.objects.create_user('supplier_test', 'sup_test@example.com', 'suppass')
        self.supplier = Supplier.objects.create(user=self.supplier_user, name='TestSupplier')
        
    def test_supplier_without_docs_is_not_approved(self):
        self.assertFalse(self.supplier.has_uploaded_all_required_docs())
        self.assertFalse(self.supplier.is_approved_to_bid())
        
    def test_supplier_with_pending_docs_is_not_approved(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from procurement.models import SupplierDocument
        
        doc_reg = SupplierDocument.objects.create(
            supplier=self.supplier,
            document_type='business_registration',
            file=SimpleUploadedFile('reg.pdf', b'content', content_type='application/pdf'),
            status='PENDING'
        )
        doc_ins = SupplierDocument.objects.create(
            supplier=self.supplier,
            document_type='insurance',
            file=SimpleUploadedFile('ins.pdf', b'content', content_type='application/pdf'),
            status='PENDING'
        )
        
        self.assertTrue(self.supplier.has_uploaded_all_required_docs())
        self.assertFalse(self.supplier.is_approved_to_bid())
        
    def test_supplier_with_approved_docs_is_approved(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from procurement.models import SupplierDocument
        
        SupplierDocument.objects.create(
            supplier=self.supplier,
            document_type='business_registration',
            file=SimpleUploadedFile('reg.pdf', b'content', content_type='application/pdf'),
            status='APPROVED'
        )
        SupplierDocument.objects.create(
            supplier=self.supplier,
            document_type='insurance',
            file=SimpleUploadedFile('ins.pdf', b'content', content_type='application/pdf'),
            status='APPROVED'
        )
        
        self.assertTrue(self.supplier.has_uploaded_all_required_docs())
        self.assertTrue(self.supplier.is_approved_to_bid())
        
    def test_unverified_supplier_cannot_access_bidding(self):
        c = Client()
        c.login(username='supplier_test', password='suppass')
        
        # Access bid page should redirect to supplier_documents
        resp = c.get(f'/tender/{self.tender.id}/bids/')
        self.assertRedirects(resp, '/supplier/documents/')
        
    def test_verified_supplier_can_access_bidding(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from procurement.models import SupplierDocument
        
        SupplierDocument.objects.create(
            supplier=self.supplier,
            document_type='business_registration',
            file=SimpleUploadedFile('reg.pdf', b'content', content_type='application/pdf'),
            status='APPROVED'
        )
        SupplierDocument.objects.create(
            supplier=self.supplier,
            document_type='insurance',
            file=SimpleUploadedFile('ins.pdf', b'content', content_type='application/pdf'),
            status='APPROVED'
        )
        
        c = Client()
        c.login(username='supplier_test', password='suppass')
        
        resp = c.get(f'/tender/{self.tender.id}/bids/')
        # Should render bid form successfully (status 200) instead of redirecting
        self.assertEqual(resp.status_code, 200)


from django.contrib import admin
from .models import (
    Tender, Airline, Supplier, Airport, Currency, 
    UnitOfMeasure, GlobalConfig, TaxTemplate, 
    VolumeRequirement, Bid, SupplierDocument
)

class SupplierDocumentInline(admin.TabularInline):
    model = SupplierDocument
    extra = 0
    readonly_fields = ('uploaded_at',)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    # Updated to use names you prefer in list_display while providing the logic below
    list_display = ('name', 'related_user', 'contact_email', 'bidding_status')
    search_fields = ('name', 'user__username', 'user__email')
    inlines = [SupplierDocumentInline]

    def related_user(self, obj):
        return obj.user.username
    related_user.short_description = 'Username'

    def contact_email(self, obj):
        return obj.user.email
    contact_email.short_description = 'Email'

    def bidding_status(self, obj):
        return "Verified & Active" if obj.is_approved_to_bid() else "Pending Review/Documents"
    bidding_status.short_description = 'Bidding Status'

@admin.register(Airline)
class AirlineAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_username')
    
    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Username'

@admin.register(Airport)
class AirportAdmin(admin.ModelAdmin):
    list_display = ('icao_code', 'iata_code', 'name', 'country')
    search_fields = ('icao_code', 'iata_code', 'name')

@admin.register(TaxTemplate)
class TaxTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'airport', 'category', 'calculation_method', 'rate', 'currency')
    list_filter = ('airport', 'category', 'calculation_method')

@admin.register(VolumeRequirement)
class VolumeRequirementAdmin(admin.ModelAdmin):
    # Updated to your preferred list_display and list_filter
    # Added volume_usg as well so you can verify the normalization math
    list_display = ('tender', 'airline', 'airport', 'volume_amount', 'uom', 'volume_usg')
    list_filter = ('tender', 'airport', 'airline')

@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    # Updated to show the fields you requested including round_number
    list_display = ('tender', 'supplier', 'airport', 'differential_price', 'currency', 'uom', 'round_number')
    list_filter = ('tender', 'supplier', 'round_number')
    readonly_fields = ('taxes_total',)

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'exchange_rate_to_usd', 'symbol')

@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('code', 'conversion_to_usg')

@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'current_round')
    list_editable = ('current_round',)
    list_filter = ('current_round',)
    search_fields = ('title',)

admin.site.register(GlobalConfig)
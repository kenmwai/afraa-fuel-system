from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.forms import modelformset_factory
from .models import VolumeRequirement, Bid, Airport, UnitOfMeasure, SupplierDocument

class VolumeForm(forms.ModelForm):
    class Meta:
        model = VolumeRequirement
        # We renamed 'estimated_volume_liters' to 'volume_amount'
        fields = ['airport', 'volume_amount', 'uom'] 
        widgets = {
            'airport': forms.Select(attrs={'class': 'form-control'}),
            'volume_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Amount'}),
            'uom': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Order dropdowns alphabetically to make selection easy
        self.fields['airport'].queryset = Airport.objects.all().order_by('iata_code', 'icao_code')
        self.fields['uom'].queryset = UnitOfMeasure.objects.all().order_by('code')

    def has_changed(self):
        if not self.instance.pk:
            airport_val = self.data.get(self.add_prefix('airport'))
            volume_val = self.data.get(self.add_prefix('volume_amount'))
            if not airport_val and not volume_val:
                return False
        return super().has_changed()

from django.forms import BaseModelFormSet

class BaseVolumeFormSet(BaseModelFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        
        airports = []
        for form in self.forms:
            if not form.has_changed():
                continue
            if self.can_delete and self._should_delete_form(form):
                continue
            airport = form.cleaned_data.get('airport')
            if airport:
                if airport in airports:
                    form.add_error('airport', 'You can only submit one volume per location.')
                else:
                    airports.append(airport)

# The Grid Factory
VolumeFormSet = modelformset_factory(
    VolumeRequirement,
    form=VolumeForm,
    formset=BaseVolumeFormSet,
    extra=5, 
    can_delete=True
)

class BidForm(forms.ModelForm):
    class Meta:
        model = Bid
        # Updated to include new Currency and Unit fields
        fields = [
            'price_basis', 
            'differential_price', 
            'currency',
            'exchange_rate',
            'uom',
            'taxes_total', 
            'tax_breakdown',
            'volume_percentage_offered',
            'payment_terms'
        ]

class UserRegistrationForm(UserCreationForm):
    ACCOUNT_TYPE_CHOICES = [
        ('airline', 'Airline'),
        ('supplier', 'Supplier')
    ]
    
    email = forms.EmailField(required=True)
    account_type = forms.ChoiceField(choices=ACCOUNT_TYPE_CHOICES, widget=forms.RadioSelect, required=True)
    company_name = forms.CharField(max_length=100, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email']


class SupplierDocumentForm(forms.ModelForm):
    class Meta:
        model = SupplierDocument
        fields = ['document_type', 'file']
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

from decimal import Decimal

# Standard Conversion Factors to US Gallons (Base Unit)
# 1 Liter = 0.264172 US Gallons
# 1 Imperial Gallon = 1.20095 US Gallons
# 1 Metric Tonne = Approx 330.25 US Gallons (Jet A1 Density Dependent)

UNIT_FACTORS = {
    'USG': Decimal('1.0'),            # Base Unit
    'L': Decimal('0.264172'),         # 1 L = 0.264 USG
    'IG': Decimal('1.20095'),         # 1 Imp Gal = 1.2 USG
    'MT': Decimal('330.25'),          # 1 MT = 330.25 USG (Approx)
}

def convert_currency(amount, from_curr, to_curr, rate_to_usd):
    """
    Helper to convert currencies if needed in future logic.
    """
    if amount == 0: return Decimal('0.00')
    return amount # Placeholder for complex logic
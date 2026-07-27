from decimal import Decimal, InvalidOperation
from .models import Currency, UnitOfMeasure, GlobalConfig
from .services import get_exchange_rate

class BidAnalyzer:
    @staticmethod
    def analyze_bid(bid, target_curr_code, target_uom_obj, tender, vol_list):
        """
        Analyzes a single bid and normalizes its pricing.
        """
        try:
            ref = Decimal(bid.reference_price_amount or 0)
        except (InvalidOperation, TypeError):
            ref = Decimal(0)
            
        try:
            diff = Decimal(bid.differential_price or 0)
        except (InvalidOperation, TypeError):
            diff = Decimal(0)

        base = ref + diff

        # Currency Conversion
        exch = Decimal(1)
        if target_curr_code:
            try:
                # Use stored bid exchange rate if non-default, otherwise dynamically fetch
                if getattr(bid, 'exchange_rate', None) and Decimal(bid.exchange_rate) != Decimal(1):
                    exch = Decimal(bid.exchange_rate)
                else:
                    curr_code = bid.currency.code if bid.currency else None
                    if curr_code:
                        rate_info = get_exchange_rate(curr_code, target_curr_code)
                        exch = Decimal(rate_info.get('rate', 1))
            except Exception:
                exch = Decimal(1)

        standardized_base = base * exch
        standardized_diff = diff * exch

        # Unit Conversion
        if target_uom_obj and bid.uom and getattr(bid.uom, 'conversion_to_usg', None) and getattr(target_uom_obj, 'conversion_to_usg', None):
            try:
                ratio = Decimal(bid.uom.conversion_to_usg) / Decimal(target_uom_obj.conversion_to_usg)
                standardized_base = standardized_base * ratio
                standardized_diff = standardized_diff * ratio
            except Exception:
                pass

        # Demand Weight Calculation required early for taxes
        demand_usg = sum([v.volume_usg for v in vol_list])
        actual_demand_usg = Decimal(demand_usg) if demand_usg else Decimal(1)
        uptakes = sum([v.uptakes_per_year or 0 for v in vol_list]) or 1
        demand_usg_per_uptake = actual_demand_usg / Decimal(uptakes)
        weight = actual_demand_usg * Decimal(uptakes)

        # Taxes
        raw_tax_items, legacy_fees_raw = bid.get_parsed_taxes()
        standardized_fees = Decimal(0)
        categorized_taxes = {
            'included': [],
            'excluded': [],
            'conditional': []
        }

        if not raw_tax_items and legacy_fees_raw:
             # Very old fallback
             standardized_fees = Decimal(legacy_fees_raw)

        for tax in raw_tax_items:
            amt = Decimal(str(tax['amount']))
            
            # 1. Tax Currency Conversion
            tax_exch = Decimal(1)
            tax_curr_code = tax.get('currency')
            if target_curr_code and tax_curr_code and tax_curr_code != target_curr_code:
                try:
                    rate_info = get_exchange_rate(tax_curr_code, target_curr_code)
                    tax_exch = Decimal(rate_info.get('rate', 1))
                except Exception:
                    pass
            converted_amt = amt * tax_exch
            
            # 2. Tax Unit Conversion
            tax_uom_code = tax.get('uom', 'USG')
            if target_uom_obj and tax_uom_code != getattr(target_uom_obj, 'code', ''):
                try:
                    t_uom_obj = UnitOfMeasure.objects.get(code=tax_uom_code)
                    ratio = Decimal(t_uom_obj.conversion_to_usg) / Decimal(target_uom_obj.conversion_to_usg)
                    converted_amt = converted_amt * ratio
                except Exception:
                    pass

            # 3. Method calculation (UNIT vs UPTAKE)
            if tax.get('method') == 'UPTAKE':
                # Distribute the uptake fee across units for standard IP metric
                converted_amt = converted_amt / demand_usg_per_uptake

            processed_tax = {
                'name': tax['name'],
                'original_amount': float(amt),
                'original_currency': tax_curr_code,
                'method': tax.get('method', 'UNIT'),
                'computed_amount': float(converted_amt)
            }

            # 4. Bucket by category
            cat = tax.get('category', 'MANDATORY_INCLUDED')
            if cat == 'MANDATORY_INCLUDED':
                standardized_fees += converted_amt
                categorized_taxes['included'].append(processed_tax)
            elif cat == 'MANDATORY_EXCLUDED':
                categorized_taxes['excluded'].append(processed_tax)
            else:
                categorized_taxes['conditional'].append(processed_tax)

        # Financial Adjustment (Credit Benefit)
        fin_adj = Decimal(0)
        try:
            from procurement.models import GlobalConfig
            apr_config = GlobalConfig.objects.get(key='cost_of_credit_apr')
            corate = Decimal(apr_config.value) / Decimal(100) # Convert percentage to decimal if they enter 5 for 5%
        except Exception:
            corate = Decimal(0)
            
        base_credit_period = getattr(bid, 'credit_period', 0) or 0
        invoicing_freq = getattr(bid, 'invoicing_frequency', 0) or 0
        total_effective_credit_days = (Decimal(invoicing_freq) / Decimal(2)) + Decimal(base_credit_period)
        
        if corate and total_effective_credit_days > 0:
            # (Cost) * (Annual Rate) * (Effective Days / 360)
            fin_adj = (standardized_base + standardized_fees) * corate * (total_effective_credit_days / Decimal(360))

        # Net Landed Price exactly matches physical pricing without abstract financial reductions
        total_landed = standardized_base + standardized_fees

        return {
            'supplier': str(bid.supplier),
            'original_bid': f"{bid.price_basis} {ref}",
            'original_differential': float(diff),
            'standardized_base_price': float(standardized_base),
            'standardized_differential': float(standardized_diff),
            'fees_and_taxes': float(standardized_fees),
            'categorized_taxes': categorized_taxes,
            'fx_source': {
                'bid_exchange_rate': float(getattr(bid, 'exchange_rate', 1)), 
                'currency_code': getattr(bid.currency, 'code', None), 
                'currency_fx_to_usd': float(getattr(getattr(bid, 'currency', None), 'exchange_rate_to_usd', 1))
            },
            'credit_period': float(total_effective_credit_days),
            'fin_adj': float(fin_adj),
            'total_landed_cost': float(total_landed),
            'weight': float(weight),
            'weighted_total': float((total_landed or Decimal(0)) * (weight or Decimal(0)))
        }
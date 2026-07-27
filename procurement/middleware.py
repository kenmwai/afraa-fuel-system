import re

from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


class RoleAccessMiddleware:
    """Middleware to enforce role-based access to tender pages.

    - /tender/<id>/bids/  -> suppliers only (or superusers)
    - /tender/<id>/volumes/ -> airlines only (or superusers)
    - /tender/<id>/analysis/ -> superusers only
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.bid_re = re.compile(r'^/tender/\d+/bids/?')
        self.vol_re = re.compile(r'^/tender/\d+/volumes/?')
        self.analysis_re = re.compile(r'^/tender/\d+/analysis/?')

    def __call__(self, request):
        path = request.path

        # Allow unauthenticated users to proceed to login flow (views handle @login_required)
        if self.bid_re.match(path):
            if not getattr(request.user, 'is_authenticated', False):
                return self.get_response(request)
            if not (hasattr(request.user, 'supplier') or request.user.is_superuser):
                messages.error(request, 'Access Denied: Only Suppliers may access the Bid Submission page.')
                return redirect(reverse('dashboard'))
            if hasattr(request.user, 'supplier') and not request.user.is_superuser:
                if not request.user.supplier.is_approved_to_bid():
                    messages.error(request, 'Access Denied: You must upload all required verification documents and receive administrator approval before placing bids.')
                    return redirect(reverse('supplier_documents'))


        if self.vol_re.match(path):
            if not getattr(request.user, 'is_authenticated', False):
                return self.get_response(request)
            if not (hasattr(request.user, 'airline') or request.user.is_superuser):
                messages.error(request, 'Access Denied: Only Airlines may access the Volume Submission page.')
                return redirect(reverse('dashboard'))

        if self.analysis_re.match(path):
            if not getattr(request.user, 'is_authenticated', False):
                return self.get_response(request)
            if not request.user.is_superuser:
                messages.error(request, 'Access Denied: Admin privileges required.')
                return redirect(reverse('dashboard'))

        return self.get_response(request)

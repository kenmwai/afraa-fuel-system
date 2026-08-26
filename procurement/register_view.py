from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from .forms import UserRegistrationForm
from .models import Supplier, Airline


def register(request):
    """Simple registration view that uses procurement.forms.UserRegistrationForm.

    - Creates a Django User via the form.
    - Creates an Airline or Supplier profile linked to the user using the company_name field.
    - Logs the user in and redirects to the dashboard (adjust as needed).
    """
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data['email']
            user.save()

            account_type = form.cleaned_data.get('account_type')
            company_name = form.cleaned_data.get('company_name')

            if account_type == 'supplier':
                Supplier.objects.create(user=user, name=company_name)
            else:
                Airline.objects.create(user=user, name=company_name)

            messages.success(request, "Registration successful. You are now logged in.")
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})

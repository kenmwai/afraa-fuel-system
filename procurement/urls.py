from django.urls import path
from . import views

urlpatterns = [
    # Registration
    path('register/', views.register, name='register'),
    
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Airline: Submit Volumes
    path('tender/<int:tender_id>/volumes/', views.submit_volumes, name='submit_volumes'),
    
    # Supplier: Submit Bids
    path('tender/<int:tender_id>/bids/', views.submit_bids, name='submit_bids'),
    
    # Admin: Analysis Matrix (The missing link!)
    path('tender/<int:tender_id>/analysis/', views.analysis_dashboard, name='analysis_dashboard'),

    # Supplier: Bidding Dashboard
    path('tender/<int:tender_id>/my-dashboard/', views.supplier_analysis_dashboard, name='supplier_analysis_dashboard'),

    # Airline: Bidding Dashboard
    path('tender/<int:tender_id>/airline-dashboard/', views.airline_analysis_dashboard, name='airline_analysis_dashboard'),

    # Admin: Toggle Live Ranking
    path('tender/<int:tender_id>/toggle-live-ranking/', views.toggle_live_ranking, name='toggle_live_ranking'),

    # Admin: Reports & Insights
    path('tender/<int:tender_id>/reports/', views.reports_insights, name='reports_insights'),

    # Supplier: Document Uploads
    path('supplier/documents/', views.supplier_documents, name='supplier_documents'),

    # Admin Settings Dashboard
    path('admin-console/', views.admin_console, name='admin_console'),
]
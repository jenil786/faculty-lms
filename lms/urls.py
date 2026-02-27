#pass1
from . import views
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from lms import views


urlpatterns = [
    # existing urls ...
    path('login/', auth_views.LoginView.as_view(
        template_name='lms/login.html'
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

urlpatterns = [
    # General Routes
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='lms/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('reports/hod/', views.hod_leave_report, name='hod_leave_report'),
    path('reports/hr/', views.hr_leave_report, name='hr_leave_report'),
    path('', views.home, name='home'), #pass
    # #password section start #pass
    path('request-password/', views.request_password, name='request_password'), #pass
    path('admin/send-password/<int:request_id>/', views.admin_send_password, name='admin_send_password'), #pass1
    # Role-Based Dashboards
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('hod-dashboard/', views.hod_dashboard, name='hod_dashboard'),
    path('hr-dashboard/', views.hr_dashboard, name='hr_dashboard'),
    path('faculty-dashboard/', views.faculty_dashboard, name='faculty_dashboard'),
     # Apply Leave
    path('leave/approve/<int:leave_id>/', views.approve_leave, name='approve_leave'),
    path('leave/reject/<int:leave_id>/', views.reject_leave, name='reject_leave'),
    path('apply-leave/', views.apply_leave, name='apply_leave'),
    path('my-leaves/', views.my_leaves, name='my_leaves'),
    path('hod/leaves/', views.hod_pending_leaves, name='hod_pending_leaves'),
    path('hod/approve/<int:leave_id>/', views.hod_approve_leave, name='hod_approve_leave'),
    path('hod/reject/<int:leave_id>/', views.hod_reject_leave, name='hod_reject_leave'),
    path('hr/leaves/', views.hr_pending_leaves, name='hr_pending_leaves'),
    path('hr/approve/<int:leave_id>/', views.hr_approve_leave, name='hr_approve_leave'),
    path('hr/reject/<int:leave_id>/', views.hr_reject_leave, name='hr_reject_leave'),
    path('reports/my-leaves/', views.faculty_leave_report, name='faculty_leave_report'),
    path('reports/hod/', views.hod_leave_report, name='hod_leave_report'),
    path('reports/hr/', views.hr_leave_report, name='hr_leave_report'),
    path('reports/export/pdf/<str:scope>/', views.export_leave_report_pdf, name='export_pdf'),
    path('hr/staff-balances/', views.hr_staff_balances, name='hr_staff_balances'),  
    path('export-pdf/<str:scope>/', views.export_leave_report_pdf, name='export_leave_report_pdf'),

]




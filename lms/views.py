
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from .models import FacultyProfile, LeaveRequest, LeaveBalance, Department, PasswordRequest
from django.views.decorators.http import require_POST
from django.db.models import Count, Sum, F, Q
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.db import transaction
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from .forms import LeaveRequestForm, PasswordRequestForm
from django.db.models.functions import Coalesce
from django.db.models import FloatField
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.conf import settings
import pytz 

import string #pass2
import random #pass2

# #password section start #pass2
@login_required 
def admin_send_password(request, request_id): 
    if request.user.facultyprofile.role != 'ADMIN': 
        return HttpResponseForbidden("Access Denied") 
    
    pass_req = get_object_or_404(PasswordRequest, id=request_id) 
    
    try: 
        # Match by email provided in the request
        profile = FacultyProfile.objects.get(faculty_email=pass_req.email) 
        user = profile.user 
        
        # 1. Generate a new random password
        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10)) 
        
        # 2. Update the User's password in Django Auth
        user.set_password(new_password) 
        user.save() 
        
        # 3. Prepare and send the email
        subject = 'SSIT LMS - Your Account Credentials' 
        message = (
            f"Hello {profile.faculty_name},\n\n"
            f"Your account has been processed. Your new login credentials are:\n"
            f"Username: {user.username}\n"
            f"Password: {new_password}\n\n"
            f"Please login and change your password immediately for security."
        ) 
        
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [pass_req.email]) 
        
        pass_req.is_resolved = True 
        pass_req.save() 
        messages.success(request, f"New credentials generated and sent to {pass_req.email}") 
        
    except FacultyProfile.DoesNotExist: 
        messages.error(request, "No Faculty Profile found with that email address.") 
        
    return redirect('/admin/lms/passwordrequest/') 
# #password section end #pass2

# #password section start #pass
def request_password(request):
    if request.method == 'POST':
        form = PasswordRequestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your password request has been sent to the Admin.")
        else:
            for error in form.errors.values():
                messages.error(request, error)
        return redirect('login')
    return redirect('login')
# #password section end #pass

def get_profile(user):
    try:
        return FacultyProfile.objects.select_related(
            'department',
        ).get(user=user)
    except FacultyProfile.DoesNotExist:
        return None

@login_required
def get_hod_profile(request):
    profile = get_profile(request.user)
    if not profile:
        return None

    if profile.role != 'HOD':
        return None

    # ✅ ensure this HOD is assigned to the department
    if not profile.department:
        return None

    if profile.department.hod != request.user:
        return None

    return profile

@login_required
def dashboard_redirect(request):
    profile = get_profile(request.user)

    if not profile:
        return HttpResponse("No Faculty Profile found for this user.", status=403)

    if profile.role == 'ADMIN':
        return redirect('admin_dashboard')

    if profile.role == 'HOD':
        # 🔒 HARD CHECK: must be actual department HOD
        if profile.department and profile.department.hod == request.user:
            return redirect('hod_dashboard')
        # fallback → faculty
        return redirect('faculty_dashboard')

    if profile.role == 'HR':
        return redirect('hr_dashboard')

    return redirect('faculty_dashboard')


# 2️⃣ DASHBOARDS
@login_required
def admin_dashboard(request):
    context = {
        'total_faculty': FacultyProfile.objects.count(),
        'pending_leaves': LeaveRequest.objects.filter(status='PENDING').count(),
        'pending_password_requests': PasswordRequest.objects.filter(is_resolved=False).count(), # Added #pass
        'all_faculty': FacultyProfile.objects.all(),
    }
    return render(request, 'lms/admin_dashboard.html', context)



@login_required
def faculty_dashboard(request):
    # Fetch balance safely
    balance, created = LeaveBalance.objects.get_or_create(user=request.user)
    return render(request, 'lms/faculty_dashboard.html', {'balance': balance})

@login_required
def apply_leave(request):
    try:
        profile = request.user.facultyprofile
    except FacultyProfile.DoesNotExist:
        messages.error(request, "Faculty Profile not found. Please contact Admin.")
        return redirect('dashboard')
    balance, created = LeaveBalance.objects.get_or_create(user=request.user)# self
    if request.method == 'POST':
        # Pass the POST data and the user to the form
        form = LeaveRequestForm(request.POST, user=request.user)
        
        # --- THE FIX ---
        # We must link the user to the model instance BEFORE validation
        # so that model's clean() method can access 'self.user'
        form.instance.user = request.user 
        
        if form.is_valid():
            try:
                leave = form.save(commit=False)

                # Role-based logic
                if profile.role == 'HOD':
                    leave.status = 'HOD_APPROVED'
                    leave.hod = request.user
                else:
                    leave.status = 'PENDING'

                # Since we already ran is_valid(), full_clean() will work now
                leave.full_clean()
                leave.save()
                
                messages.success(request, "Leave application submitted successfully!")
        # Instead of redirecting to 'my_leaves', return the same page
        # The JavaScript in the template will now catch this message and show the modal
                return render(request, 'lms/apply_leave.html', {'form': LeaveRequestForm(user=request.user)})
            
            except ValidationError as e:
                form.add_error(None, e)
    else:
        form = LeaveRequestForm(user=request.user)

    return render(request, 'lms/apply_leave.html', {'form': form})

@login_required
def approve_leave(request, leave_id):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponse("Unauthorized", status=403)
    
    try:
        leave = LeaveRequest.objects.get(id=leave_id)
        if leave.user.facultyprofile.department == profile.department:
            leave.status = 'HOD_APPROVED'
            leave.hod = request.user
            leave.save()
        return redirect('hod_dashboard')
    except LeaveRequest.DoesNotExist:
        return HttpResponse("Leave request not found", status=404)

@login_required
def reject_leave(request, leave_id):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponse("Unauthorized", status=403)
    
    try:
        leave = LeaveRequest.objects.get(id=leave_id)
        if leave.user.facultyprofile.department == profile.department:
            leave.status = 'REJECTED'
            leave.hod = request.user
            leave.save()
        return redirect('hod_dashboard')
    except LeaveRequest.DoesNotExist:
        return HttpResponse("Leave request not found", status=404)

def home(request):
    return HttpResponse("Faculty LMS Home Page")

#working
@login_required
def my_leaves(request):
    balance, created = LeaveBalance.objects.get_or_create(user=request.user)
    # Base queryset
    leaves_queryset = LeaveRequest.objects.filter(user=request.user).order_by('-applied_on')
    
    # --- ADD PAGINATION ---
    paginator = Paginator(leaves_queryset, 25) # 25 records per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'lms/my_leaves.html', {'leaves': page_obj})

def hod_dashboard(request):
    user = request.user

    if not user.is_authenticated:
        raise PermissionDenied

    profile = getattr(user, 'facultyprofile', None)
    if not profile or profile.role != 'HOD':
        raise PermissionDenied

    # 🔒 Cross-verify department HOD
    department = profile.department
    if not department or department.hod != user:
        raise PermissionDenied

    # Add this line to fetch balance for the HOD
    balance, created = LeaveBalance.objects.get_or_create(user=user)

    return render(request, 'lms/hod_dashboard.html', {
        'department': department,
        'balance': balance  # Pass balance to context
    })

@login_required
def hod_pending_leaves(request):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("HOD access only")

    leaves = LeaveRequest.objects.filter(
        status='PENDING',
        user__facultyprofile__department=profile.department
    ).exclude(user=request.user)
    # For each leave, calculate how many OTHER people from same dept are off at that time
    for leave in leaves:
        overlap_count = LeaveRequest.objects.filter(
            user__facultyprofile__department=profile.department,
            status__in=['APPROVED', 'HR_APPROVED'] # Only count already confirmed leaves
        ).filter(
            # Standard overlap logic: (StartA <= EndB) and (EndA >= StartB)
            Q(from_date__lte=leave.to_date) & Q(to_date__gte=leave.from_date)
        ).exclude(user=leave.user).count()
        
        leave.overlap_count = overlap_count # Attach it to the object for the template

    return render(request, 'lms/hod_pending_leaves.html', {'leaves': leaves})


def hod_approve_leave(request, leave_id):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("Not allowed")

    leave = LeaveRequest.objects.get(id=leave_id)

    if leave.user.facultyprofile.department != profile.department:
        return HttpResponseForbidden("Cross-department action blocked")

    leave.status = 'HOD_APPROVED'
    leave.hod = request.user
    leave.save()

    return redirect('hod_pending_leaves')


@login_required
def hod_reject_leave(request, leave_id):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("Not allowed")

    leave = LeaveRequest.objects.get(id=leave_id)

    if leave.user.facultyprofile.department != profile.department:
        return HttpResponseForbidden("Cross-department action blocked")

    # MODIFIED LOGIC TO CAPTURE REASON:
    if request.method == 'POST':
        reason = request.POST.get('rejection_reason')
        if not reason:
            messages.error(request, "Please provide a reason for rejection.")
            return redirect('hod_pending_leaves')
            
        leave.status = 'REJECTED'
        leave.rejection_reason = reason  # Save the reason
        leave.hod = request.user
        leave.save()
        messages.success(request, f"Leave for {leave.user.username} has been rejected.")

    return redirect('hod_pending_leaves')

@login_required
def hr_dashboard(request):
    # Security check using your existing get_profile logic
    profile = get_profile(request.user)
    if not profile or profile.role != 'HR':
        return HttpResponseForbidden("HR only")
    
    # Combined into one block to preserve FloatField precision
    usage_data = LeaveBalance.objects.aggregate(
        total_cl=Coalesce(Sum('cl_used'), 0.0, output_field=FloatField()),
        total_el=Coalesce(Sum('el_used'), 0.0, output_field=FloatField()),
        total_ml=Coalesce(Sum('ml_used'), 0.0, output_field=FloatField())
    )

    # 2. Data for Bar Chart (Your existing logic)
    dept_pending = LeaveRequest.objects.filter(status='HR_APPROVED').values(
        dept_name=F('user__facultyprofile__department__name')
    ).annotate(
        count=Count('id')
    ).order_by('-count')

    context = {
        'usage_data': usage_data,
        'dept_pending': list(dept_pending),
    }
    return render(request, 'lms/hr_dashboard.html', context)

@login_required
def hr_pending_leaves(request):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("You are not authorized")

    # 1. Capture the GET data
    faculty_query = request.GET.get('faculty_query', '')
    dept_filter = request.GET.get('dept', '')
    status_filter = request.GET.get('status', 'pending') 

    # --- CURRENT LOGIC MAINTAINED ---
    if status_filter == 'approved':
        leaves = LeaveRequest.objects.filter(status='HR_APPROVED')
    else:
        from django.db.models import Q
        leaves = LeaveRequest.objects.filter(
            Q(user__facultyprofile__role='HOD', status='HOD_APPROVED') | 
            Q(user__facultyprofile__role='FACULTY', status='HOD_APPROVED')
        )

    if faculty_query:
        leaves = leaves.filter(user__username__icontains=faculty_query)
    if dept_filter:
        leaves = leaves.filter(user__facultyprofile__department=dept_filter)
    
    if status_filter == 'approved':
        leaves = LeaveRequest.objects.filter(status='HR_APPROVED')

    # 2. Loop through each leave to calculate overlaps
    for leave in leaves:
        from django.db.models import Q
        
        # --- REFINED LOGIC: ONLY APPROVED/PENDING OVERLAPS WITHIN SAME DEPT ---
        # This removes REJECTED leaves from the count entirely.
        # It only shows people who are actually confirmed or cleared to be away.
        overlaps = LeaveRequest.objects.filter(
            ~Q(id=leave.id),
            from_date__lte=leave.to_date,
            to_date__gte=leave.from_date,
            # We filter for Approved or HOD Cleared only; Rejected is excluded.
            status__in=['HOD_APPROVED', 'HR_APPROVED'],
            # Strict department check to avoid cross-department confusion.
            user__facultyprofile__department=leave.user.facultyprofile.department
        ).select_related('user')

        leave.overlap_count = overlaps.count()
        leave.overlapping_names = ", ".join([o.user.username for o in overlaps])

    # 4. Pass variables to context
    return render(request, 'lms/hr_pending_leaves.html', {
        'leaves': leaves,
        'faculty_query': faculty_query,
        'dept_filter': dept_filter,
        'status_filter': status_filter
    })

@login_required
@require_POST
def hr_approve_leave(request, leave_id):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("Not allowed")

    with transaction.atomic():
        # Use select_for_update to prevent race conditions during deduction
        leave = LeaveRequest.objects.select_for_update().get(id=leave_id)
        
        if leave.status != 'HR_APPROVED':
            # Handle Half Day vs Full Day logic
            if leave.half_day:
                duration = 0.5
            else:
                duration = float((leave.to_date - leave.from_date).days + 1)
            
            try:
                balance = leave.user.leavebalance
                
                # Check specific type balance availability
                available = 0
                if leave.leave_type == 'CL':
                    available = balance.cl_balance - balance.cl_used
                elif leave.leave_type == 'EL':
                    available = balance.el_balance - balance.el_used
                elif leave.leave_type == 'ML':
                    available = balance.ml_balance - balance.ml_used

                if available >= duration:
                    # 1. Update status
                    leave.status = 'HR_APPROVED'
                    leave.save()

                    # 2. Deduct from specific balance category (FIXED ERROR HERE)
                    if leave.leave_type == 'CL':
                        balance.cl_used += duration
                    elif leave.leave_type == 'EL':
                        balance.el_used += duration
                    elif leave.leave_type == 'ML':
                        balance.ml_used += duration
                    
                    balance.save()
                    
                    messages.success(request, f"Leave approved. {duration} days deducted from {leave.user.username}'s {leave.leave_type} balance.")
                else:
                    messages.error(request, f"Cannot approve: {leave.user.username} has insufficient {leave.leave_type} balance.")
            
            except LeaveBalance.DoesNotExist:
                messages.error(request, "User has no Leave Balance record. Please contact Admin.")

    return redirect('hr_pending_leaves')

@login_required
@require_POST
def hr_reject_leave(request, leave_id):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("Not allowed")

    if request.method == 'POST':
        leave = get_object_or_404(LeaveRequest, id=leave_id)
        
        # Capture the reason from the form
        reason = request.POST.get('rejection_reason')
        
        leave.status = 'REJECTED'
        leave.rejection_reason = reason  # Save it to the model field
        leave.save()  # This triggers the refund logic we fixed earlier
        
        messages.success(request, f"Leave request for {leave.user.username} has been rejected.")
        return redirect('hr_dashboard') # Or your specific HR pending view
@login_required
@transaction.atomic
def hr_staff_balances(request):
    # Security: Ensure only HR or Admin can access this page
    if not hasattr(request.user, 'facultyprofile') or request.user.facultyprofile.role not in ['HR', 'ADMIN']:
        messages.error(request, "You do not have permission to access the Staff Balance page.")
        return redirect('dashboard')
        
    # Handle Bulk Reset POST request
    if request.method == 'POST' and 'bulk_reset' in request.POST:
        try:
            # Convert inputs to float for validation
            new_cl = float(request.POST.get('cl_amount', 12))
            new_el = float(request.POST.get('el_amount', 10))
            new_ml = float(request.POST.get('ml_amount', 10))
            
            # Validation: Must be between 0.1 and 25
            amounts = [new_cl, new_el, new_ml]
            if any(a <= 0 for a in amounts) or any(a > 25 for a in amounts):
                messages.error(request, "Error: Leave values must be greater than 0 and not exceed 25 days.")
            else:
                LeaveBalance.objects.all().update(
                    cl_balance=new_cl, cl_used=0.0,
                    el_balance=new_el, el_used=0.0,
                    ml_balance=new_ml, ml_used=0.0
                )
                messages.success(request, f"Global reset complete: CL({new_cl}), EL({new_el}), ML({new_ml})")
        except (ValueError, TypeError):
            messages.error(request, "Invalid numeric values provided.")
            
        return redirect('hr_staff_balances')

    # Fetch all balances
    balances = LeaveBalance.objects.select_related('user').all()
    
    # --- UPDATED LOGIC TO AVOID ATTRIBUTE ERROR ---
    # We use setattr to bypass the property restriction, 
    # OR better yet, if the property already exists in models.py, 
    # we don't need to calculate it here at all.
    
    # If you want to keep the manual calculation logic:
    processed_balances = []
    for bal in balances:
        # We attach these as temporary attributes to the object
        # but we use different names if the property already exists,
        # or we simply rely on the model property if it's already there.
        try:
            bal.cl_neg = -float(bal.cl_used)
            bal.el_neg = -float(bal.el_used)
            bal.ml_neg = -float(bal.ml_used)
        except AttributeError:
            # If the model already handles this via @property, we just pass
            pass
        processed_balances.append(bal)
        
    return render(request, 'lms/hr_staff_balances.html', {'balances': processed_balances})
    
# =========================
# REPORTS MODULE – FACULTY
# =========================
@login_required
def faculty_leave_report(request):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'FACULTY':
        return HttpResponseForbidden("Not allowed")

    # Start with base queryset
    leaves_queryset = LeaveRequest.objects.filter(user=request.user).order_by('-applied_on')

    month = request.GET.get('month')
    year = request.GET.get('year')

    if month:
        leaves_queryset = leaves_queryset.filter(from_date__month=month)

    if year:
        leaves_queryset = leaves_queryset.filter(from_date__year=year)

    # ✅ ALWAYS defined based on filtered queryset
    summary = leaves_queryset.values('status').annotate(total=Count('id')).order_by('status')

    # --- PAGINATION LOGIC ---
    # Set up paginator with 25 leaves per page
    paginator = Paginator(leaves_queryset, 25)
    page_number = request.GET.get('page')
    leaves_obj = paginator.get_page(page_number)

    return render(request, 'lms/reports/faculty_leave_report.html', {
        'leaves': leaves_obj,  # Pass the paginated object instead of the raw queryset
        'summary': summary,
        'selected_month': month,
        'selected_year': year,  
    })

@login_required
def hod_leave_report(request):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("Not allowed")

    leaves = LeaveRequest.objects.filter(
        user__facultyprofile__department=profile.department
    ).select_related('user__facultyprofile')

    # --- FILTERS ---
    month = request.GET.get('month')
    if month:
        leaves = leaves.filter(from_date__month=month)

    year = request.GET.get('year')
    if year:
        leaves = leaves.filter(from_date__year=year)
        
    # NEW: Search Faculty Filter
    faculty_query = request.GET.get('faculty_query', '')
    if faculty_query:
        leaves = leaves.filter(
            Q(user__username__icontains=faculty_query) | 
            Q(user__first_name__icontains=faculty_query) | 
            Q(user__last_name__icontains=faculty_query)
        )

    # ✅ Summary (Calculate before pagination to include all filtered records)
    summary = leaves.values('status').annotate(total=Count('id'))

    # --- PAGINATION ---
    paginator = Paginator(leaves, 25) # Show 25 records per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    month_list = [str(i) for i in range(1, 13)]

    context = {
        'leaves': page_obj, # Pass the paginated object
        'summary': summary,
        'selected_month': month,
        'selected_year': year,
        'faculty_query': faculty_query,
        'month_list': month_list, # Pass query back to template
    }

    return render(request, 'lms/reports/hod_leave_report.html', context)

@login_required
def hr_leave_report(request):
    profile = FacultyProfile.objects.get(user=request.user)

    if profile.role != 'HR':
        return HttpResponseForbidden("Not allowed")

    # Start with all records
    leaves = LeaveRequest.objects.all().select_related('user__facultyprofile')

    # 1. Capture Filter Parameters
    month = request.GET.get('month')
    year = request.GET.get('year')
    faculty_query = request.GET.get('faculty_query', '')
    dept_filter = request.GET.get('dept', '')
    departments = Department.objects.all()
    # 2. Apply Date Filters
    if month:
        leaves = leaves.filter(from_date__month=month)
    if year:
        leaves = leaves.filter(from_date__year=year)

    # 3. Apply New Search Filters
    if faculty_query:
        leaves = leaves.filter(
            Q(user__username__icontains=faculty_query) | 
            Q(user__first_name__icontains=faculty_query) | 
            Q(user__last_name__icontains=faculty_query)
        )

    if dept_filter:
        leaves = leaves.filter(user__facultyprofile__department=dept_filter)

    # 4. Generate Summary (Based on filtered results)
    summary = leaves.values('status').annotate(total=Count('id'))
    # --- ADD PAGINATION LOGIC HERE ---
    paginator = Paginator(leaves, 25) # Show 25 records per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    # ---------------------------------
    context = {
        'leaves': page_obj,
        'summary': summary,
        'month_filter': month,
        'departments': departments,
        'year_filter': year,
        'faculty_query': faculty_query,
        'dept_filter': dept_filter,
    }

    return render(request, 'lms/reports/hr_leave_report.html', context)


@login_required
def export_leave_report_pdf(request, scope):
    # --- GET USER PROFILE ---
    try:
        profile = FacultyProfile.objects.get(user=request.user)
    except FacultyProfile.DoesNotExist:
        return HttpResponseForbidden("Profile not found")

    # --- NEW: CAPTURE FILTERS (Same logic as your web views) ---
    faculty_query = request.GET.get('faculty_query', '')
    dept_filter = request.GET.get('dept', '')
    month = request.GET.get('month')
    year = request.GET.get('year')

    # --- SCOPE LOGIC (UNCHANGED) ---
    if profile.role == 'FACULTY':
        leaves = LeaveRequest.objects.filter(user=request.user)
    elif profile.role == 'HOD':
        if scope == 'self':
            leaves = LeaveRequest.objects.filter(user=request.user)
        elif scope == 'department':
            leaves = LeaveRequest.objects.filter(
                user__facultyprofile__department=profile.department
            )
        else:
            return HttpResponseForbidden("Invalid export scope")
    elif profile.role == 'HR':
        leaves = LeaveRequest.objects.all()
    else:
        return HttpResponseForbidden("Not allowed")

    # --- NEW: APPLY THE FILTERS TO THE PDF QUERYSET ---
    if faculty_query:
        leaves = leaves.filter(
            Q(user__username__icontains=faculty_query) | 
            Q(user__first_name__icontains=faculty_query) | 
            Q(user__last_name__icontains=faculty_query)
        )
    if dept_filter:
        leaves = leaves.filter(user__facultyprofile__department=dept_filter)
    if month:
        leaves = leaves.filter(from_date__month=month)
    if year:
        leaves = leaves.filter(from_date__year=year)

    # Order by most recent applied date
    leaves = leaves.order_by('-applied_on')

    # --- PDF RESPONSE SETUP (UNCHANGED) ---
    response = HttpResponse(content_type='application/pdf')
    filename = f"Leave_Report_{scope}_{request.user.username}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # --- STYLING & DOCUMENT SETUP (UNCHANGED) ---
    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=30, leftMargin=30,
        topMargin=40, bottomMargin=30
    )
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontSize=18,
        textColor=colors.HexColor("#2c3e50"), spaceAfter=10
    )
    subtitle_style = ParagraphStyle(
        'SubStyle', parent=styles['Normal'], fontSize=10,
        textColor=colors.grey, spaceAfter=20
    )
    remark_style = ParagraphStyle(
        'RemarkStyle', parent=styles['Normal'], fontSize=8,
        leading=10, alignment=0 
    )

    # --- HEADER SECTION ---
    elements.append(Paragraph(f"Leave History Report", title_style))
    elements.append(Paragraph(f"Scope: {scope.capitalize()} | Generated for: {request.user.username}", subtitle_style))
    elements.append(Spacer(1, 0.2 * inch))

    # --- DATA PREPARATION ---
    data = [['Faculty', 'From Date', 'To Date', 'Status', 'Admin Remarks']]
    for leave in leaves:
        reason = leave.rejection_reason if leave.status == 'REJECTED' and leave.rejection_reason else "---"
        remark_p = Paragraph(reason, remark_style)
        data.append([
            leave.user.username,
            leave.from_date.strftime('%d-%m-%Y'), # Updated: DD-MM-YYYY
            leave.to_date.strftime('%d-%m-%Y'),   # Updated: DD-MM-YYYY
            leave.get_status_display(),
            remark_p 
        ])

    col_widths = [100, 85, 85, 85, 180]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#475569")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.5 * inch))
    
    # Use real timestamp instead of date_joined
    india_tz = pytz.timezone('Asia/Kolkata')
    now = timezone.now().astimezone(india_tz)
    footer_text = Paragraph(f"Report generated on: {now.strftime('%d-%m-%Y %I:%M %p')} IST", subtitle_style)
    elements.append(footer_text)
    print(f"DEBUG: Params received: {request.GET}")
    doc.build(elements)
    return response
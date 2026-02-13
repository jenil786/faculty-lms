from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import FacultyProfile, LeaveRequest
from .forms import LeaveRequestForm
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Count
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from django.core.exceptions import PermissionDenied

def get_profile(user):
    try:
        return FacultyProfile.objects.select_related(
            'department', 'college'
        ).get(user=user)
    except FacultyProfile.DoesNotExist:
        return None


# HELPER: Verify HOD Status
#working
"""@login_required
def get_hod_profile(request):
    try:
        profile = FacultyProfile.objects.get(user=request.user)
        if profile.role == 'HOD':
            return profile
    except FacultyProfile.DoesNotExist:
        pass
    return None
"""
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



# 1️⃣ DASHBOARD REDIRECT
#working
"""@login_required
def dashboard_redirect(request):
    try:
        profile = FacultyProfile.objects.get(user=request.user)
        role_map = {
            'ADMIN': 'admin_dashboard',
            'HOD': 'hod_dashboard',
            'HR': 'hr_dashboard',
            'FACULTY': 'faculty_dashboard',
        }
        return redirect(role_map.get(profile.role, 'faculty_dashboard'))
    except FacultyProfile.DoesNotExist:
        return HttpResponse("No Faculty Profile found for this user.")"""

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
        'all_faculty': FacultyProfile.objects.all(),
    }
    return render(request, 'lms/admin_dashboard.html', context)


@login_required
def faculty_dashboard(request):
    return render(request, 'lms/faculty_dashboard.html')

@login_required
def apply_leave(request):
    profile = FacultyProfile.objects.get(user=request.user)

    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, user=request.user)
        if form.is_valid():
            leave = form.save(commit=False)

            # 🔐 System-controlled fields
            leave.user = request.user
            leave.college = profile.college          
            leave.department = profile.department    

            # Role-based auto approval
            if profile.role == 'HOD':
                leave.status = 'HOD_APPROVED'
                leave.hod = request.user
            else:
                leave.status = 'PENDING'

            leave.save()
            return redirect('my_leaves')
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
    leaves = LeaveRequest.objects.filter(user=request.user).order_by('-applied_on')
    return render(request, 'lms/my_leaves.html', {'leaves': leaves})


"""@login_required
def hod_dashboard(request):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponse("Unauthorized: Only HODs can access this page.", status=403)"""
"""@login_required
def hod_dashboard(request):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("Not assigned as HOD for any department")
    
    if not profile.department:
        return HttpResponse("Error: You are an HOD but not assigned to any department.")
    

    pending_requests = LeaveRequest.objects.filter(
        user__facultyprofile__department=profile.department,
        status='PENDING'
    ).exclude(user=request.user)

    return render(request, 'lms/hod_dashboard.html', {
        'profile': profile,
        'pending_requests': pending_requests,
        'department_name': profile.department.name
    })"""


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

    return render(request, 'lms/hod_dashboard.html', {
        'department': department
    })



"""@login_required
def hod_pending_leaves(request):
    try:
        profile = FacultyProfile.objects.get(user=request.user)
    except FacultyProfile.DoesNotExist:
        return HttpResponseForbidden("Profile not found")

    if profile.role != 'HOD':
        return HttpResponseForbidden("You are not authorized")
#new lines
    if not profile.department:
        return HttpResponse("Department not assigned yet.")
#
    leaves = LeaveRequest.objects.filter(
        status='PENDING',
        user__facultyprofile__department=profile.department
    ).exclude(user=request.user)  

    return render(request, 'lms/hod_pending_leaves.html', {'leaves': leaves})"""

@login_required
def hod_pending_leaves(request):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("HOD access only")

    leaves = LeaveRequest.objects.filter(
        status='PENDING',
        user__facultyprofile__department=profile.department
    ).exclude(user=request.user)

    return render(request, 'lms/hod_pending_leaves.html', {'leaves': leaves})

"""@login_required
def hod_approve_leave(request, leave_id):
    leave = LeaveRequest.objects.get(id=leave_id)
    profile = FacultyProfile.objects.get(user=request.user)

    if profile.role != 'HOD':
        return HttpResponseForbidden("Not allowed")

    leave.status = 'HOD_APPROVED'
    leave.hod = request.user
    leave.save()

    return redirect('hod_pending_leaves')"""
@login_required
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


"""@login_required
def hod_reject_leave(request, leave_id):
    leave = LeaveRequest.objects.get(id=leave_id)
    profile = FacultyProfile.objects.get(user=request.user)

    if profile.role not in ['FACULTY', 'HOD', 'HR']:
       return HttpResponseForbidden("Not allowed")

    leave.status = 'REJECTED'
    leave.save()

    return redirect('hod_pending_leaves')"""
@login_required
def hod_reject_leave(request, leave_id):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("Not allowed")

    leave = LeaveRequest.objects.get(id=leave_id)

    if leave.user.facultyprofile.department != profile.department:
        return HttpResponseForbidden("Cross-department action blocked")

    leave.status = 'REJECTED'
    leave.hod = request.user
    leave.save()

    return redirect('hod_pending_leaves')



"""@login_required
def hr_dashboard(request):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("You are not authorized")"""
@login_required
def hr_dashboard(request):
    profile = get_profile(request.user)
    if not profile or profile.role != 'HR':
        return HttpResponseForbidden("HR only")


    return render(request, 'lms/hr_dashboard.html')


@login_required
def hr_pending_leaves(request):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("You are not authorized")

   
    leaves = LeaveRequest.objects.filter(
    status='HOD_APPROVED',
    college=profile.college
).filter(#new lines from here from .filter ( <- is old
    status__in=['PENDING', 'HOD_APPROVED']
)#

    return render(request, 'lms/hr_pending_leaves.html', {'leaves': leaves})


@login_required
@require_POST
def hr_approve_leave(request, leave_id):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("Not allowed")

    leave = LeaveRequest.objects.get(id=leave_id)
    leave.status = 'HR_APPROVED'
    leave.save()
    return redirect('hr_pending_leaves')


@login_required
@require_POST
def hr_reject_leave(request, leave_id):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'HR':
        return HttpResponseForbidden("Not allowed")

    leave = LeaveRequest.objects.get(id=leave_id)
    leave.status = 'REJECTED'
    leave.save()
    return redirect('hr_pending_leaves')

@login_required
def dashboard(request):
    try:
        profile = FacultyProfile.objects.get(user=request.user)
    except FacultyProfile.DoesNotExist:
        return HttpResponse("Faculty profile not found")

    if profile.role == 'ADMIN':
        return redirect('admin_dashboard')
    elif profile.role == 'HOD' and profile.department and profile.department.hod == request.user:   # new
       return redirect('hod_dashboard')   # new
    elif profile.role == 'HR':
        return redirect('hr_dashboard')
    else:
        return redirect('faculty_dashboard')
    
# =========================
# REPORTS MODULE – FACULTY
# =========================

@login_required
def faculty_leave_report(request):
    profile = FacultyProfile.objects.get(user=request.user)
    if profile.role != 'FACULTY':
        return HttpResponseForbidden("Not allowed")

    leaves = LeaveRequest.objects.filter(user=request.user)

    month = request.GET.get('month')
    year = request.GET.get('year')

    if month:
        leaves = leaves.filter(from_date__month=month)

    if year:
        leaves = leaves.filter(from_date__year=year)

    # ✅ ALWAYS defined
    summary = leaves.values('status').annotate(total=Count('id'))

    return render(request, 'lms/reports/faculty_leave_report.html', {
        'leaves': leaves,
        'summary': summary,
        'selected_month': month,
        'selected_year': year,  
    })


"""@login_required
def hod_leave_report(request):
    profile = FacultyProfile.objects.get(user=request.user)

    if profile.role != 'HOD':
        return HttpResponseForbidden("Not allowed")"""
@login_required
def hod_leave_report(request):
    profile = get_hod_profile(request)
    if not profile:
        return HttpResponseForbidden("Not allowed")


    leaves = LeaveRequest.objects.filter(
        user__facultyprofile__department=profile.department
    )

    # filters
    month = request.GET.get('month')
    if month:
        leaves = leaves.filter(from_date__month=month)

    year = request.GET.get('year')
    if year:
        leaves = leaves.filter(from_date__year=year)

    # ✅ summary
    summary = leaves.values('status').annotate(total=Count('id'))

    context = {
        'leaves': leaves,
        'summary': summary,
        'selected_month': month,
        'selected_year': year,
    }

    return render(request, 'lms/reports/hod_leave_report.html', context)


@login_required
def hr_leave_report(request):
    profile = FacultyProfile.objects.get(user=request.user)

    if profile.role != 'HR':
        return HttpResponseForbidden("Not allowed")

    """leaves = LeaveRequest.objects.all()"""
    leaves = LeaveRequest.objects.filter(college=profile.college)

    # filters
    month = request.GET.get('month')
    if month:
        leaves = leaves.filter(from_date__month=month)

    year = request.GET.get('year')
    if year:
        leaves = leaves.filter(from_date__year=year)

    # ✅ summary
    summary = leaves.values('status').annotate(total=Count('id'))

    context = {
        'leaves': leaves,
        'summary': summary,
        'selected_month': month,
        'selected_year': year,
    }

    return render(request, 'lms/reports/hr_leave_report.html', context)

@login_required
def export_leave_report_pdf(request, scope):
    profile = FacultyProfile.objects.get(user=request.user)

    # FACULTY → only own
    if profile.role == 'FACULTY':
        leaves = LeaveRequest.objects.filter(user=request.user)

    # HOD logic (FIXED)
    elif profile.role == 'HOD':
        if scope == 'self':
            leaves = LeaveRequest.objects.filter(user=request.user)
        elif scope == 'department':
            leaves = LeaveRequest.objects.filter(
                user__facultyprofile__department=profile.department
            )
        else:
            return HttpResponseForbidden("Invalid export scope")

    # HR → all
    elif profile.role == 'HR':
        """leaves = LeaveRequest.objects.all()"""
        leaves = LeaveRequest.objects.filter(college=profile.college)


    else:
        return HttpResponseForbidden("Not allowed")

    # -------- PDF BUILD --------
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="leave_report.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4)

    data = [['Faculty', 'Role', 'From', 'To', 'Status']]

    for leave in leaves:
        fp = getattr(leave.user, 'facultyprofile', None)
        role = fp.role if fp else 'N/A'

        data.append([
            leave.user.username,
            role,
            leave.from_date.strftime('%d-%m-%Y'),
            leave.to_date.strftime('%d-%m-%Y'),
            leave.get_status_display()
        ])

    table = Table(data)
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
    ]))

    doc.build([table])
    return response

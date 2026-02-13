from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from .models import Department, LeaveBalance, LeaveRequest, FacultyProfile
from django.db import transaction
from .models import College
from django.shortcuts import render, redirect
from django.urls import path
from django.urls import reverse
from django.contrib.auth import get_user_model
User = get_user_model()
"""admin.site.register(College)"""

# -----------------------------
# College
# -----------------------------
@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    # We changed 'location' to 'name' to stop the error
    list_display = ('name',) 

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, 'facultyprofile', None)
        if profile and profile.role in ['HR', 'ADMIN']:
            return True
        return False

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, 'facultyprofile', None)
        return profile and profile.role in ['HR', 'ADMIN']

# -----------------------------
# Department
# -----------------------------

class DepartmentAdminForm(ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

    def clean_hod(self):
        hod = self.cleaned_data.get('hod')
        if hod:
            if not hasattr(hod, 'facultyprofile'):
                raise ValidationError("Selected user has no Faculty Profile.")
            if hod.facultyprofile.role not in ['FACULTY', 'HOD']:
                raise ValidationError("Only Faculty members can be assigned as HOD.")
        return hod
    
# -----------------------------
# Department
# -----------------------------
class DepartmentAdminForm(ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

    def clean_hod(self):
        hod = self.cleaned_data.get('hod')
        if hod:
            if not hasattr(hod, 'facultyprofile'):
                raise ValidationError("Selected user has no Faculty Profile.")
            if hod.facultyprofile.role not in ['FACULTY', 'HOD']:
                raise ValidationError("Only Faculty members can be assigned as HOD.")
        return hod

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'college', 'hod')
    readonly_fields = ('hod',)
    form = DepartmentAdminForm
    list_select_related = ('college', 'hod') # Fixes speed

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "hod":
            kwargs["queryset"] = User.objects.filter(facultyprofile__role__in=['FACULTY', 'HOD'])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        profile = getattr(request.user, 'facultyprofile', None)
        if profile and profile.role in ['HR', 'ADMIN']:
            return qs.filter(college=profile.college)
        return qs.none()

    def has_module_permission(self, request):
        if request.user.is_superuser: return True
        profile = getattr(request.user, 'facultyprofile', None)
        return profile and profile.role in ['HR', 'ADMIN']
    

# -----------------------------
# Leave Request
# -----------------------------


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'college', 'from_date', 'to_date', 'status', 'applied_on')
    list_filter = ('status',)
    search_fields = ('user__username',)
    ordering = ('-applied_on',)

    def get_queryset(self, request):
        # This one line does BOTH: Security and Speed (select_related)
        qs = super().get_queryset(request).select_related('user', 'college', 'user__facultyprofile')

        if request.user.is_superuser:
            return qs

        profile = getattr(request.user, 'facultyprofile', None)
        if not profile: return qs.none()

        if profile.role in ['ADMIN', 'HR']:
            return qs.filter(college=profile.college)
        if profile.role == 'HOD':
            return qs.filter(user__facultyprofile__department=profile.department)
        if profile.role == 'FACULTY':
            return qs.filter(user=request.user)
        return qs.none()
    

    # -----------------------------
    # Field-level control
    # -----------------------------

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser or not obj:
            return []

        profile = getattr(request.user, 'facultyprofile', None)
        if not profile:
            return []

        base_fields = [
            'user',
            'college',
            'from_date',
            'to_date',
            'reason',
            'applied_on',
        ]

        if profile.role == 'FACULTY':
            return base_fields + ['status', 'hod']

        if profile.role == 'HOD':
            return base_fields

        if profile.role == 'HR':
            return base_fields + ['hod']

        return []


    # -----------------------------
    # Auto-assign user for faculty
    # -----------------------------
def save_model(self, request, obj, form, change):
    profile = getattr(request.user, 'facultyprofile', None)

    if profile and profile.role == 'FACULTY' and not change:
        obj.user = request.user
        obj.college = profile.college

    if profile and profile.role == 'HOD' and obj.status == 'HOD_APPROVED':
        obj.hod = request.user

    super().save_model(request, obj, form, change)



# -----------------------------
# Leave Balance
# -----------------------------
@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'total_leaves',
        'used_leaves',
        'remaining_leaves',
    )
    list_select_related = ('user',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

# -----------------------------
# Faculty Profile
# -----------------------------


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
    # This is the most important line. It MUST include all 3 relationships.
    list_select_related = ('user', 'college', 'department')
    list_display = ('user', 'role', 'college', 'department')  
    list_filter = ('role', 'college', 'department')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'college', 'department')

    """
    # 2. Advanced speed fix (The "Force" method)
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 
            'college', 
            'department',
            'department__college' # This fetches the college via the department
        )"""
    
    # This prevents the "Black Screen" / Slow loading on searches
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    def save_model(self, request, obj, form, change):
        try:
            with transaction.atomic():
                super().save_model(request, obj, form, change)

                # Explicit HOD sync
                if hasattr(obj, "_sync_department_hod"):
                    obj._sync_department_hod()
                    
                # 🔵 FIX-5: Explicit HR sync
                if hasattr(obj, "_sync_college_hr"):
                    obj._sync_college_hr() 
                
                # Informational message for downgrade
                if change and 'role' in form.changed_data:
                    if form.initial.get('role') == 'HOD' and obj.role != 'HOD':
                        messages.warning(
                            request,
                            "This faculty was downgraded from HOD. "
                            "Department HOD assignment has been cleared."
                        )

                messages.success(
                    request,
                    "Faculty profile saved successfully."
                )

                if change and 'role' in form.changed_data:
                   # 🔵 FIX-5: HR downgrade message (NEW)
                    if form.initial.get('role') == 'HR' and obj.role != 'HR':
                        messages.warning(
                            request,
                            "This faculty was downgraded from HR. "
                            "College HR assignment has been cleared."
                     )


        except ValidationError as e:
            form.add_error(None, e)
            messages.error(request, e)
            return
       

    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:object_id>/confirm-change/',
                self.admin_site.admin_view(self.confirm_change),
                name='lms_facultyprofile_confirm_change'
            ),
        ]
        return custom_urls + urls
    
    def _requires_confirmation(
        self,
        old_role,
        old_department,
        old_college,
        new_role,
        new_department,
        new_college,
    ):
        messages = []

        if old_role != new_role and {'HOD', 'HR'} & {old_role, new_role}:
            messages.append(f"Role change: {old_role} → {new_role}")

        if new_role == 'HOD' and old_department != new_department:
            messages.append(
                f"HOD department change: {old_department} → {new_department}"
            )

        if new_role == 'HR' and old_college != new_college:
            messages.append(
                f"HR college change: {old_college} → {new_college}"
            )

        return bool(messages), messages

    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method != 'POST' or not object_id:
            return super().changeform_view(request, object_id, form_url, extra_context)

        obj = self.get_object(request, object_id)

        old_role = obj.role
        old_department = obj.department
        old_college = obj.college

        FormClass = self.get_form(request)
        form = FormClass(request.POST, instance=obj)

        if not form.is_valid():
            return super().changeform_view(request, object_id, form_url, extra_context)

        new_role = form.cleaned_data.get('role')
        new_department = form.cleaned_data.get('department')
        new_college = form.cleaned_data.get('college')

        requires_confirm, reasons = self._requires_confirmation(
            old_role,
            old_department,
            old_college,
            new_role,
            new_department,
            new_college,
        )

        if requires_confirm and not request.POST.get('_confirmed'):
            request.session['confirm_reasons'] = reasons
            request.session['pending_form_data'] = request.POST.dict()

            confirm_url = reverse(
                'admin:lms_facultyprofile_confirm_change',
                args=[object_id],
            )
            return redirect(confirm_url)

        return super().changeform_view(request, object_id, form_url, extra_context)
#   newnew   nnnnnnnnnnnnnnn
    def confirm_change(self, request, object_id):
        obj = self.get_object(request, object_id)
        
        if request.method == 'POST':
            # 1. Retrieve the saved POST data from session
            original_data = request.session.get('pending_form_data', {})

            if not original_data:
                return redirect('../change/')

            # 2. Inject the original data and the confirmation flag back into the request
            request.POST = request.POST.copy()
            request.POST.clear()
            request.POST.update(original_data)
            request.POST['_confirmed'] = '1'

            # 3. Clean up the session so it doesn't trigger again
            request.session.pop('pending_form_data', None)
            request.session.pop('confirm_reasons', None)

            # 4. Hand back to changeform_view which will now see '_confirmed' and save
            return self.changeform_view(
                request, 
                str(object_id), 
                form_url='', 
                extra_context=None
            )

        return render(
            request,
            'admin/lms/facultyprofile/confirm_change.html',
            {
                'object': obj,
                'opts': self.model._meta,
                'title': 'Confirmation Required',
            }
        )
   
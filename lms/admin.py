from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.forms import ModelForm
from .models import Department, LeaveBalance, LeaveRequest, FacultyProfile, PasswordRequest
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils.html import format_html
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.template.response import TemplateResponse
from django.conf import settings
from django.contrib.auth.hashers import check_password
User = get_user_model()



@admin.register(PasswordRequest)
class PasswordRequestAdmin(admin.ModelAdmin):
    list_display = ('user_identity', 'email', 'mobile', 'request_date', 'is_resolved', 'send_password_button')
    list_filter = ('is_resolved',)
    
    def send_password_button(self, obj):
        if not obj.is_resolved:
            url = reverse('admin:admin_manual_reset', args=[obj.id])
            return format_html('<a class="button" style="background-color: #417690; color: white; padding: 3px 10px;" href="{}">Process Reset</a>', url)
        return format_html('<span style="color: green; font-weight: bold;">✔ Sent</span>')
    
    send_password_button.short_description = "Action"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:request_id>/manual-reset/', self.admin_site.admin_view(self.manual_reset_view), name='admin_manual_reset'),
        ]
        return custom_urls + urls

    def manual_reset_view(self, request, request_id):
        obj = self.get_object(request, request_id)
        
        if request.method == 'POST':
            new_pw = request.POST.get('new_password')
            
            # IMPROVED LOOKUP: Check by identity (username) OR email
            user_obj = User.objects.filter(username=obj.user_identity).first() or \
                    User.objects.filter(email=obj.email).first()
            
            if user_obj and new_pw:
                # --- STRICT VALIDATION START ---
                if not check_password(new_pw, user_obj.password):
                    messages.error(request, "Mismatch Error: The password entered does not match the one currently saved in the User's profile.")
                # --- STRICT VALIDATION END ---
                else:
                    try:
                        # Validate password complexity (Django built-in)
                        validate_password(new_pw, user=user_obj)
                        
                        # 1. Update Database (Re-saving to be safe)
                        user_obj.set_password(new_pw)
                        user_obj.save()
                        
                        # 2. Send the Email
                        subject = "Your SSIT LMS Login Credentials"
                        message = (
                            f"Hello {user_obj.username},\n\n"
                            f"As per your request, the Admin has verified and updated your password.\n"
                            f"New Login Password: {new_pw}\n\n"
                            f"Regards,\nSSIT Admin Team"
                        )
                        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [obj.email])
                        
                        # 3. Mark request as resolved
                        obj.is_resolved = True
                        obj.save()
                        
                        messages.success(request, f"Password verified and emailed to {obj.email}")
                        return redirect('admin:lms_passwordrequest_changelist')
                        
                    except ValidationError as e:
                        messages.error(request, f"Security Error: {', '.join(e.messages)}")
                    except Exception as e:
                        messages.error(request, f"An unexpected error occurred: {str(e)}")
            else:
                # This is the error you were seeing. 
                # It triggers if user_obj is None or if the input box was empty.
                messages.error(request, "Error: User record could not be located in the database. Please check the username.")

        context = {
            **self.admin_site.each_context(request),
            'object': obj,
            'opts': self.model._meta,
            'app_label': self.model._meta.app_label,
            'title': 'Manual Password Reset',
        }
        return TemplateResponse(request, "admin/lms/passwordrequest/manual_reset.html", context)
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
    list_display = ('name', 'hod')
    readonly_fields = ('hod',)
    form = DepartmentAdminForm
    list_select_related = ('hod',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "hod":
            kwargs["queryset"] = User.objects.filter(facultyprofile__role__in=['FACULTY', 'HOD'])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: 
            return qs
        profile = getattr(request.user, 'facultyprofile', None)
        # If user is HR or ADMIN, they see all departments
        if profile and profile.role in ['HR', 'ADMIN']:
            return qs
        # Otherwise, they see nothing (or you can return qs.filter(...) for specific logic)
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
    list_display = ('id', 'user', 'from_date', 'to_date', 'status', 'applied_on')
    list_filter = ('status',)
    search_fields = ('user__username',)
    ordering = ('-applied_on',)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('user', 'user__facultyprofile')

        if request.user.is_superuser:
            return qs

        profile = getattr(request.user, 'facultyprofile', None)
        if not profile: 
            return qs.none()

        # --- HOD VIEW ---
        # HOD sees only PENDING leaves from their own department
        if profile.role == 'HOD':
            return qs.filter(
                user__facultyprofile__department=profile.department,
                status='PENDING'
            ).exclude(user=request.user) # Hide their own leaves from this view

        # --- HR VIEW (The Fix) ---
        # HR sees: 
        # 1. Any leave from a user with role 'HOD' (direct path)
        # 2. Leaves from 'FACULTY' ONLY IF already 'HOD_APPROVED'
        if profile.role == 'HR':
            from django.db.models import Q
            return qs.filter(
                Q(user__facultyprofile__role='HOD', status='PENDING') | 
                Q(user__facultyprofile__role='FACULTY', status='HOD_APPROVED')
            )

        # Faculty: See their own requests
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
            
        if profile and profile.role == 'HOD' and obj.status == 'HOD_APPROVED':
            obj.hod = request.user
        if change:  # Only check if editing an existing request
            old_obj = LeaveRequest.objects.get(pk=obj.pk)
            
            # Logic: If status JUST changed to HR_APPROVED
            if old_obj.status != 'HR_APPROVED' and obj.status == 'HR_APPROVED':
                balance, created = LeaveBalance.objects.get_or_create(user=obj.user)
                
                # --- NEW DEDUCTION CALCULATION ---
                if obj.half_day:
                    num_days = 0.5
                else:
                    num_days = float((obj.to_date - obj.from_date).days + 1)
                
                # Deduct based on leave type
                if obj.leave_type == 'CL':
                    balance.cl_used += num_days
                elif obj.leave_type == 'EL':
                    balance.el_used += num_days
                elif obj.leave_type == 'ML':
                    balance.ml_used += num_days
                
                balance.save()
                messages.success(request, f"Leave approved. {num_days} days deducted from {obj.user.username}'s balance.")
        super().save_model(request, obj, form, change)



# -----------------------------
# Leave Balance
# -----------------------------
@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    # Fix: Added 'el_used', 'ml_used' and corrected the list
    list_display = (
        'user', 
        'cl_balance', 
        'cl_used', 
        'el_balance', 
        'el_used',
        'ml_balance', 
        'ml_used',
        'remaining_leaves' # This calls the @property from your model
    )
    list_select_related = ('user',)
    
    # Organizes the admin edit page into sections
    fieldsets = (
        ('User Info', {'fields': ('user',)}),
        ('Casual Leave (CL)', {'fields': ('cl_balance', 'cl_used')}),
        ('Earned Leave (EL)', {'fields': ('el_balance', 'el_used')}),
        ('Medical Leave (ML)', {'fields': ('ml_balance', 'ml_used')}),
    )
    
    # cl_used, el_used, ml_used are read-only so they can't be manually faked in admin
    readonly_fields = ('cl_used', 'el_used', 'ml_used')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
# #password section end #pass
# -----------------------------
# Faculty Profile
# -----------------------------


@admin.register(FacultyProfile)
class FacultyProfileAdmin(admin.ModelAdmin):
    # This is the most important line. It MUST include all 3 relationships.
    list_select_related = ('user', 'department')
    list_display = ('user', 'role', 'department', 'faculty_mobile') #pass
    list_filter = ('role',  'department')
   # UPDATED: for_emergency_name #pass2
    search_fields = (
        'user__username', 'user__first_name', 'user__last_name', 
        'faculty_name', 'faculty_mobile', 'for_emergency_name'
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'department')

    def save_model(self, request, obj, form, change):
        try:
            with transaction.atomic():
                # --- START LEAVE REQUEST DEDUCTION LOGIC ---
                # Check if we are editing an existing LeaveRequest
                if isinstance(obj, LeaveRequest) and change:
                    old_obj = LeaveRequest.objects.get(pk=obj.pk)
                    
                    # Deduct only if status just changed to HR_APPROVED
                    if old_obj.status != 'HR_APPROVED' and obj.status == 'HR_APPROVED':
                        balance, _ = LeaveBalance.objects.get_or_create(user=obj.user)
                        
                        # Calculate duration using your logic
                        if obj.half_day:
                            num_days = 0.5
                        else:
                            num_days = float((obj.to_date - obj.from_date).days + 1)
                        
                        # Specific field deduction
                        if obj.leave_type == 'CL':
                            balance.cl_used += num_days
                        elif obj.leave_type == 'EL':
                            balance.el_used += num_days
                        elif obj.leave_type == 'ML':
                            balance.ml_used += num_days
                        
                        balance.save()
                        messages.success(request, f"Leave Approved: {num_days} days deducted from {obj.leave_type} balance.")
                # --- END LEAVE REQUEST DEDUCTION LOGIC ---

                # Call parent save
                super().save_model(request, obj, form, change)

                # --- YOUR EXISTING LOGIC BELOW ---
                # Faculty/HOD Auto-assign
                profile = getattr(request.user, 'facultyprofile', None)
                if profile and profile.role == 'FACULTY' and not change:
                    obj.user = request.user
                if profile and profile.role == 'HOD' and obj.status == 'HOD_APPROVED':
                    obj.hod = request.user

                # Explicit HOD sync (for FacultyProfile objects)
                if hasattr(obj, "_sync_department_hod"):
                    obj._sync_department_hod()

                # Role Change Messages
                if change and 'role' in form.changed_data:
                    old_role = form.initial.get('role')
                    if old_role == 'HOD' and obj.role != 'HOD':
                        messages.warning(request, "Faculty downgraded from HOD. Dept cleared.")
                    if old_role == 'HR' and obj.role != 'HR':
                        messages.warning(request, "Faculty downgraded from HR. HR cleared.")

                messages.success(request, "Profile/Request saved successfully.")

        except ValidationError as e:
            form.add_error(None, e)
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    
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
        new_role,
        new_department,
    ):
        messages = []

        if old_role != new_role and {'HOD', 'HR'} & {old_role, new_role}:
            messages.append(f"Role change: {old_role} → {new_role}")

        if new_role == 'HOD' and old_department != new_department:
            messages.append(
                f"HOD department change: {old_department} → {new_department}"
            )


        return bool(messages), messages

    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method != 'POST' or not object_id:
            return super().changeform_view(request, object_id, form_url, extra_context)

        obj = self.get_object(request, object_id)

        old_role = obj.role
        old_department = obj.department

        FormClass = self.get_form(request)
        form = FormClass(request.POST, instance=obj)

        if not form.is_valid():
            return super().changeform_view(request, object_id, form_url, extra_context)

        new_role = form.cleaned_data.get('role')
        new_department = form.cleaned_data.get('department')
        requires_confirm, reasons = self._requires_confirmation(
            old_role,
            old_department,
            new_role,
            new_department,
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
# 1. Define the Inline for Faculty Profile
class FacultyProfileInline(admin.StackedInline):
    model = FacultyProfile
    can_delete = False
    verbose_name_plural = 'Faculty Profile Details'
    fk_name = 'user'
    # Force the admin to fill this section during creation
    min_num = 1 #pass1
    validate_min = True #pass1
    extra = 0 #pass1

class UserAdmin(BaseUserAdmin):
    inlines = (FacultyProfileInline, )

    def save_formset(self, request, form, formset, change): #pass1
        """
        Modified #pass2: No longer capturing plain password.
        The system will generate one and email it via signals or views.
        """#pass 2 under 
        instances = formset.save(commit=False)
        for instance in instances:
            instance.save()
        formset.save_m2m()

admin.site.unregister(User)
admin.site.register(User, UserAdmin)
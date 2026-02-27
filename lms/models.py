from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from datetime import timedelta
from django.utils import timezone
from datetime import date, timedelta 
from django.db.models import Q
from django.core.validators import RegexValidator, EmailValidator #pass1
from django.template.response import TemplateResponse


# =========================
# Department Model
# =========================
User = get_user_model()

class Department(models.Model):
    name = models.CharField(max_length=100)
    hod = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hod_department'
    )
    def __str__(self):  
        return self.name  
    
# =========================
# Faculty Profile Model
# =========================

class FacultyProfile(models.Model):
    # =========================
    # MANDATORY PERSONAL INFO (Validated)
    # =========================
    faculty_name = models.CharField(max_length=100, blank=True, null=True)
    
    # Validates standard email format
    faculty_email = models.EmailField(
        blank=True, 
        null=True, 
        validators=[EmailValidator(message="Enter a valid email address (e.g., name@gmail.com).")]
    ) #pass1

    # Validates exactly 10 digits
    mobile_validator = RegexValidator(
        regex=r'^\d{10}$',
        message="Mobile number must be exactly 10 digits."
    ) #pass1

    faculty_mobile = models.CharField(
        max_length=15, 
        blank=True, 
        null=True, 
        validators=[mobile_validator]
    ) #pass1
   
    father_name = models.CharField(max_length=100, blank=True, null=True)
    father_mobile = models.CharField(
        max_length=15, 
        blank=True, 
        null=True, 
        validators=[mobile_validator]
    ) #pass1
    
    mother_name = models.CharField(max_length=100, blank=True, null=True)
    
    for_emergency_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_mobile = models.CharField(
        max_length=15, 
        blank=True, 
        null=True, 
        validators=[mobile_validator]
    ) #pass1

    ROLE_CHOICES = (
        ('FACULTY', 'Faculty'),
        ('HOD', 'Head of Department'),
        ('HR', 'Human Resources'),
        ('ADMIN', 'Admin'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, db_index=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True, 
        db_index=True
    )
    
    # =========================
    # VALIDATION (ADMIN SAFE)
    # =========================
    def clean(self):
        super().clean()
    # ---------- HOD validation (already exists) ----------
        if self.role == 'HOD' and self.department:
            if self.department.hod and self.department.hod != self.user:
                raise ValidationError({
                   'department': (
                    f"{self.department.name} already has an HOD "
                    f"({self.department.hod}).\n\n"
                    "Step 1: Change the existing HOD's role to FACULTY.\n"
                    "Step 2: Save.\n"
                    "Step 3: Assign the new HOD."
                )
            })


    # =========================
    # SAVE (NO LOGIC HERE)
    # =========================
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self._sync_department_hod()
        

    # =========================
    # SINGLE SOURCE OF TRUTH
    # =========================
    def _sync_department_hod(self):
        from .models import Department

        with transaction.atomic():

        # 🔴 CASE 1: Not HOD → remove from all departments
            if self.role != 'HOD':
                Department.objects.filter(hod=self.user).update(hod=None)
                return

        # 🔴 CASE 2: HOD without department → cleanup
            if not self.department:
                Department.objects.filter(hod=self.user).update(hod=None)
                return

        # 🔒 CASE 3: Prevent silent overwrite
            if (
                self.department.hod
                and self.department.hod != self.user
            ):
                raise ValidationError(
                    f"{self.department.name} already has an HOD "
                    f"({self.department.hod}). Remove the existing HOD first."
            )

        # 🔁 Remove user as HOD from other departments
        Department.objects.filter(
            hod=self.user
        ).exclude(
            pk=self.department.pk
        ).update(hod=None)

        # ✅ Assign safely
        if self.department.hod != self.user:
            self.department.hod = self.user
            self.department.save(update_fields=['hod'])


# #password section start #pass
class PasswordRequest(models.Model): #pass
    user_identity = models.CharField(max_length=100) #pass
    email = models.EmailField() #pass
    mobile = models.CharField(max_length=15, blank=True, null=True) #pass
    request_date = models.DateTimeField(auto_now_add=True) #pass
    is_resolved = models.BooleanField(default=False) #pass

    def __str__(self): #pass
        return f"Request by {self.user_identity}" #pass
# #password section end #pass


# =========================
# Leave Balance Model
# =========================
class LeaveBalance(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    # Breakdown by type (Admin can decide these)
    cl_balance = models.IntegerField(default=12, verbose_name="Casual Leave (CL)")
    el_balance = models.IntegerField(default=10, verbose_name="Earned Leave (EL)")
    ml_balance = models.IntegerField(default=10, verbose_name="Medical Leave (ML)")
    
    # Used counters
    cl_used = models.FloatField(default=0.0) # Changed to Float
    el_used = models.FloatField(default=0.0)
    ml_used = models.FloatField(default=0.0)
    @property
    def cl_used_negative(self):
        return -self.cl_used

    @property
    def ml_used_negative(self):
        return -self.ml_used

    @property
    def el_used_negative(self):
        return -self.el_used

    @property
    def remaining_leaves(self):
        # This already correctly calculates total remaining
        total_bal = self.cl_balance + self.el_balance + self.ml_balance
        total_used = self.cl_used + self.el_used + self.ml_used
        return total_bal - total_used

    def __str__(self):
        return f"{self.user.username}'s Balance"


# =========================
# Leave Request Model
# =========================
class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('HOD_APPROVED', 'HOD Approved'),
        ('HR_APPROVED', 'HR Approved'),
        ('REJECTED', 'Rejected'),
    ]
    
    LEAVE_TYPE_CHOICES = [
        ('CL', 'Casual Leave (CL)'),
        ('EL', 'Earned Leave (EL)'),
        ('ML', 'Medical Leave (ML)'),
        ('MAT', 'Maternity Leave (MAT)'),
        ('PAT', 'Paternity Leave (PAT)'),
    ]

    # Session choices adjusted to your requirement
    SESSION_CHOICES = [
        ('FULL', 'Full Day'),
        ('MORNING', 'Morning Session'),
        ('AFTERNOON', 'Afternoon Session'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='leave_requests'
    )

    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.TextField()

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    hod = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hod_approved_leaves'
    )

    half_day = models.BooleanField(default=False)
    session = models.CharField(
        max_length=10, 
        choices=SESSION_CHOICES, 
        default='FULL'
    )
    
    # Ensuring leave_type remains consistent with your current logic
    leave_type = models.CharField(max_length=10, choices=[('CL','CL'),('EL','EL'),('ML','ML')], default='CL')
    applied_on = models.DateTimeField(auto_now_add=True)
    rejection_reason = models.TextField(null=True, blank=True)

    def clean(self):
        # 1. Handle Half-Day Auto-fill (Locks TO_DATE to FROM_DATE)
        if self.half_day:
            if self.from_date:
                self.to_date = self.from_date
            # Ensure a specific session is picked if half_day is active
            if self.session == 'FULL':
                raise ValidationError("Please specify if the Half-Day is for the Morning or Afternoon session.")
        else:
            # Force FULL if half_day is not checked
            self.session = 'FULL'

        super().clean()
        if not self.from_date or not self.to_date:
            return

        # --- STRICT DATE BOUNDARY CHECKS ---
        today = date.today()
        limit_date = today + timedelta(days=60)

        if self.from_date < today:
            raise ValidationError("Cannot apply for leave in the past.")

        if self.from_date > limit_date:
            raise ValidationError(f"Leave date exceeds the 2-month window (Limit: {limit_date}).")

        # 2. Calculate duration
        duration = 0.5 if self.half_day else (self.to_date - self.from_date).days + 1
        
        # 3. Existing Duration Checks
        if not self.half_day: 
            if duration > 10:
                raise ValidationError(f"Leave duration ({duration} days) exceeds the 10-day limit.")
            if duration < 1:
                raise ValidationError("Invalid leave duration.")
            if self.to_date < self.from_date:
                raise ValidationError("To date cannot be before From date.")

        # 4. OVERLAP LOGIC (Updated for Morning/Afternoon Awareness)
        overlapping_leaves = LeaveRequest.objects.filter(
            user=self.user,
            status__in=['PENDING', 'HOD_APPROVED', 'HR_APPROVED']
        ).filter(
            Q(from_date__range=[self.from_date, self.to_date]) |
            Q(to_date__range=[self.from_date, self.to_date]) |
            Q(from_date__lte=self.from_date, to_date__gte=self.to_date)
        )

        if self.pk: 
            overlapping_leaves = overlapping_leaves.exclude(pk=self.pk)

        for existing in overlapping_leaves:
            # Conflict if any involves a FULL day
            if self.session == 'FULL' or existing.session == 'FULL':
                raise ValidationError(f"Conflict: You already have a {existing.get_session_display()} leave on {existing.from_date}.")
            
            # Conflict if both are same session on same day
            if self.from_date == existing.from_date and self.session == existing.session:
                raise ValidationError(f"Conflict: You already have a {existing.get_session_display()} applied for this date.")
        # 5. Leave Balance Validation
        if self.status != 'REJECTED':
            try:
                from .models import LeaveBalance 
                balance = LeaveBalance.objects.get(user=self.user)
                available = 0
                if self.leave_type == 'CL':
                    available = balance.cl_balance - balance.cl_used
                elif self.leave_type == 'EL':
                    available = balance.el_balance - balance.el_used
                elif self.leave_type == 'ML':
                    available = balance.ml_balance - balance.ml_used

                if duration > available:
                    raise ValidationError(f"Insufficient {self.leave_type} balance. Available: {available}, Requested: {duration}")
            except Exception:
                pass
            # --- NEW WORKFLOW VALIDATION ---
        if self.pk:
            old_instance = LeaveRequest.objects.get(pk=self.pk)
            
            if self.status == 'HR_APPROVED' and old_instance.status != 'HOD_APPROVED':
                raise ValidationError("Faculty leaves must be approved by the HOD before HR can approve them.")
            
            # If HOD rejects, it stays rejected and won't move to HR
            if old_instance.status == 'REJECTED' and self.status != 'REJECTED':
                 # Optional: prevent re-opening a rejected leave
                 pass

        super().clean()
    def save(self, *args, **kwargs):
        if self.pk:
            try:
                old_instance = LeaveRequest.objects.get(pk=self.pk)
                if self.status == 'REJECTED' and old_instance.status != 'REJECTED':
                    from .models import LeaveBalance 
                    balance, created = LeaveBalance.objects.get_or_create(user=self.user)
                    
                    duration = 0.5 if self.half_day else (self.to_date - self.from_date).days + 1
                    
                    if self.leave_type == 'CL':
                        balance.cl_used = max(0, balance.cl_used - duration)
                    elif self.leave_type == 'EL':
                        balance.el_used = max(0, balance.el_used - duration)
                    elif self.leave_type == 'ML':
                        balance.ml_used = max(0, balance.ml_used - duration)
                    
                    balance.save()
            except LeaveRequest.DoesNotExist:
                pass
        super().save(*args, **kwargs)



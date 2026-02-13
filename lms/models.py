from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import transaction

# =========================
# College Model (TOP LEVEL)
# =========================
class College(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
   

# =========================
# Department Model
# =========================



User = get_user_model()

class Department(models.Model):
    name = models.CharField(max_length=100)
    college = models.ForeignKey('College', on_delete=models.CASCADE)
    hod = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hod_department'
    )
    def __str__(self):  #new
        """return f"{self.name} ({self.college.name})" """ # working perfom drop
        return self.name  #new
# =========================
# Faculty Profile Model
# =========================

class FacultyProfile(models.Model):
    ROLE_CHOICES = (
        ('FACULTY', 'Faculty'),
        ('HOD', 'Head of Department'),
        ('HR', 'Human Resources'),
        ('ADMIN', 'Admin'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, db_index=True)
    college = models.ForeignKey('College', on_delete=models.CASCADE, db_index=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True, 
        db_index=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['college'],
                condition=models.Q(role='HR'),
                name='unique_hr_per_college'
            )
        ]

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

    # ---------- HR validation (NEW - FIX 5) ----------
        if self.role == 'HR' and self.college:
            existing_hr = FacultyProfile.objects.filter(
            role='HR',
            college=self.college
        ).exclude(pk=self.pk).first()

            if existing_hr:
                raise ValidationError({
                'college': (
                    f"{self.college.name} already has an HR "
                    f"({existing_hr.user}).\n\n"
                    "Step 1: Change the existing HR's role to FACULTY.\n"
                    "Step 2: Save.\n"
                    "Step 3: Assign the new HR."
                )
            })
       

    # =========================
    # SAVE (NO LOGIC HERE)
    # =========================
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    # 🔒 Centralized post-save sync (SAFE)
        self._sync_department_hod()
        self._sync_college_hr()

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

    def _sync_college_hr(self):
        with transaction.atomic():

        # 🔴 CASE 1: Not HR → nothing to enforce
            if self.role != 'HR':
                return

        # 🔴 CASE 2: Must belong to a college
            if not self.college:
                return

        # 🔒 Ensure ONE HR per college
        FacultyProfile.objects.filter(
            role='HR',
            college=self.college
        ).exclude(pk=self.pk).update(role='FACULTY')



# =========================
# Leave Balance Model
# =========================
class LeaveBalance(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    total_leaves = models.IntegerField(default=20)
    used_leaves = models.IntegerField(default=0)

    @property
    def remaining_leaves(self):
        return self.total_leaves - self.used_leaves

    """def __str__(self):
        return f"{self.user.username} - Remaining: {self.remaining_leaves}"""
    def __str__(self):
        return self.user.username


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

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='leave_requests'
    )

    # ✅ NEW (CRITICAL)
    college = models.ForeignKey(
        College,
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

    applied_on = models.DateTimeField(auto_now_add=True)

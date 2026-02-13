from django import forms
from django.utils import timezone
from .models import LeaveRequest
from django.db.models import Q

class LeaveRequestForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user   # 👈 store logged-in user

    class Meta:
        model = LeaveRequest
        fields = ['from_date', 'to_date', 'reason']
        widgets = {
            'from_date': forms.DateInput(attrs={'type': 'date'}),
            'to_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        today = timezone.now().date()

        if not from_date or not to_date or not self.user:
            return cleaned_data

        # ❌ Past date check
        if from_date < today:
            raise forms.ValidationError(
                "From date must be today or a future date."
            )

        # ❌ Invalid range
        if to_date < from_date:
            raise forms.ValidationError(
                "To date cannot be before From date."
            )

        # ❌ OVERLAPPING LEAVE CHECK (THIS WAS MISSING CONTEXT)
        overlapping_leaves = LeaveRequest.objects.filter(
    user=self.user,
    college=self.user.facultyprofile.college 
).exclude(  
    pk=self.instance.pk
).filter(
    Q(from_date__lte=to_date) &
    Q(to_date__gte=from_date)
)
        if overlapping_leaves.exists():
            raise forms.ValidationError(
                "You already have a leave request that overlaps with these dates."
            )

        return cleaned_data

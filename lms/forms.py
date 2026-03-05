from django import forms
from django.utils import timezone
from .models import LeaveRequest, LeaveBalance, PasswordRequest
from django.db.models import Q
from datetime import timedelta
import holidays

class LeaveRequestForm(forms.ModelForm):
    half_day = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'form-check-input',
        'id': 'halfDayCheck'
    }))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        
        if 'leave_type' in self.fields:
            self.fields['leave_type'].widget.attrs.update({'class': 'form-select'})
        
        # Add Bootstrap class to session dropdown
        if 'session' in self.fields:
            self.fields['session'].widget.attrs.update({'class': 'form-select', 'id': 'sessionSelect'})
            # We only show Morning and Afternoon for half-day selection
            self.fields['session'].choices = [
                ('MORNING', 'Morning Session'),
                ('AFTERNOON', 'Afternoon Session'),
            ]

        if 'to_date' in self.fields:
            self.fields['to_date'].required = False

    class Meta:
        model = LeaveRequest
        fields = ['from_date', 'to_date', 'leave_type', 'half_day', 'session', 'reason']
        widgets = {
            'from_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'to_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Reason...'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date = cleaned_data.get('to_date')
        leave_type = cleaned_data.get('leave_type')
        is_half_day = cleaned_data.get('half_day')
        session = cleaned_data.get('session')
        
        # --- [START] NEW HOLIDAY & SUNDAY CHECK ---
        if from_date and to_date:
            india_holidays = holidays.India()
            curr_date = from_date
            while curr_date <= to_date:
                if curr_date.weekday() == 6:
                    self.add_error('from_date', f"Sunday ({curr_date}) is a non-working day.")
                if curr_date in india_holidays:
                    self.add_error('from_date', f"{india_holidays.get(curr_date)} ({curr_date}) is a Public Holiday.")
                curr_date += timedelta(days=1)
        # --- [END] NEW HOLIDAY & SUNDAY CHECK ---
        if not from_date or not self.user:
            return cleaned_data

        today = timezone.now().date()
        limit_date = today + timedelta(days=60)

        if from_date < today:
            raise forms.ValidationError("Cannot apply for past dates.")
        
        if from_date > limit_date:
            raise forms.ValidationError(f"Cannot apply for leave more than 2 months in advance.")

        # 1. Half Day Logic
        if is_half_day:
            to_date = from_date
            cleaned_data['to_date'] = to_date
            duration = 0.5
            if not session:
                self.add_error('session', "Please select a session.")
        else:
            cleaned_data['session'] = 'FULL' # Default for full day
            if not to_date:
                self.add_error('to_date', "To date is required.")
                return cleaned_data
            if to_date < from_date:
                raise forms.ValidationError("To date cannot be before From date.")
            duration = (to_date - from_date).days + 1

        # 2. Leave Balance Check (Existing Logic)
        try:
            balance = LeaveBalance.objects.get(user=self.user)
            available = 0
            if leave_type == 'CL': available = balance.cl_balance - balance.cl_used
            elif leave_type == 'EL': available = balance.el_balance - balance.el_used
            elif leave_type == 'ML': available = balance.ml_balance - balance.ml_used
            
            if duration > available:
                raise forms.ValidationError(f"Insufficient balance. Available: {available}")
        except LeaveBalance.DoesNotExist:
            raise forms.ValidationError("Balance record not found.")

        # 3. Smart Overlap Check (FIXED FOR SAME DAY MORNING/AFTERNOON)
        overlapping = LeaveRequest.objects.filter(
            user=self.user,
            status__in=['PENDING', 'HOD_APPROVED', 'HR_APPROVED'],
            from_date__lte=to_date,
            to_date__gte=from_date
        ).exclude(pk=self.instance.pk)

        for leave in overlapping:
            # If the NEW or EXISTING leave is a Full Day, it blocks everything in that range
            if cleaned_data.get('session') == 'FULL' or leave.session == 'FULL':
                raise forms.ValidationError(f"Overlap: You have a {leave.get_session_display()} leave already.")
            
            # If both are Half Days, they only conflict if they are on the SAME day AND SAME session
            if from_date == leave.from_date and cleaned_data.get('session') == leave.session:
                raise forms.ValidationError(f"Overlap: You already applied for the {leave.get_session_display()} on this date.")

        return cleaned_data
    
    # =========================
# Password Request Form #pass1
# =========================
class PasswordRequestForm(forms.ModelForm):
    class Meta:
        model = PasswordRequest
        fields = ['user_identity', 'email', 'mobile']
        widgets = {
            'user_identity': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter your Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter your Registered Email'
            }),
            'mobile': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter your Mobile Number'
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Optional: You can check if the email exists in the User table
        # if not User.objects.filter(email=email).exists():
        #     raise forms.ValidationError("This email is not registered in our system.")
        return email
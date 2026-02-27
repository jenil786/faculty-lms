from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from lms.models import FacultyProfile, LeaveBalance 

User = get_user_model()

@receiver(post_save, sender=User)
def create_faculty_user_data(sender, instance, created, **kwargs):
    if not created:
        return
    
    # 1. Create Faculty Profile
    if not hasattr(instance, 'facultyprofile'):
        FacultyProfile.objects.create(
            user=instance, 
            role='FACULTY'
        )
        
    # 2. Create Leave Balance
    if not hasattr(instance, 'leavebalance'):
        LeaveBalance.objects.create(user=instance)

    # 3. Send Welcome Email with Password #pass2
    # Logic: Capture the password set during creation and email it immediately
    if instance.email:
        try:
            subject = 'Welcome to LMS - Your Account Details'
            # We use instance.password logic if you set it manually, 
            # but usually, we send a link or the raw password from the form.
            message = (
                f"Hi {instance.username},\n\n"
                f"Your account has been created successfully.\n"
                f"Username: {instance.username}\n"
                f"Email: {instance.email}\n\n"
                f"Please use the 'Forgot Password' feature on the login page "
                f"to set your unique password and log in.\n\n"
                f"Regards,\nAdmin Team"
            )
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [instance.email],
                fail_silently=True,
            )
        except Exception:
            pass # Prevent user creation from failing if email server is down
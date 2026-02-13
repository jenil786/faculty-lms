from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from lms.models import FacultyProfile, College

User = get_user_model()

@receiver(post_save, sender=User)
def create_faculty_profile(sender, instance, created, **kwargs):
    if not created:
        return

    # prevent duplicate profile creation
    if hasattr(instance, 'facultyprofile'):
        return

    default_college = College.objects.first()
    if not default_college:
        return  # fail safely if no college exists

    FacultyProfile.objects.create(
    user=instance,
    college=default_college,
    role='FACULTY'   # ✅ SAFE DEFAULT
)

 

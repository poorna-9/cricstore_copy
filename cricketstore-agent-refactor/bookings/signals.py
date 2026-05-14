from django.db.models.signals import post_save, post_delete
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import *
from .utils import generateslots 
from datetime import date, timedelta

@receiver(post_save, sender=User)
def create_customer(sender, instance, created, **kwargs):
    if created:
        Customer.objects.create(
            user=instance,
            name=instance.username,
            email=instance.email
        )

@receiver(post_save, sender=Ground)
def create_slots_for_new_ground(sender, instance, created, **kwargs):
    if created:
        for i in range(60):
            generateslots(instance, date.today() + timedelta(days=i))

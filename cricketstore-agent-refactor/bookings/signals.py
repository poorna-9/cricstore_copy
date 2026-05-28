from django.db import transaction
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver

from .models import Customer, Ground
from .tasks import generate_slots_for_ground


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
        transaction.on_commit(
            lambda: generate_slots_for_ground.delay(instance.pk)
        )

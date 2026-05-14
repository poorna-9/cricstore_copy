from django.core.management.base import BaseCommand
from datetime import date, timedelta
from bookings.models import Ground #type: ignore
from bookings.utils import generateslots  #type: ignore

class Command(BaseCommand):
    help = 'Generate slots for all grounds for the next day (keep rolling for 2 months)'

    def handle(self, *args, **options):
        today = date.today()
        next_day = today + timedelta(days=1)
        for ground in Ground.objects.all():
            generateslots(ground, next_day)
        self.stdout.write(self.style.SUCCESS(f'Slots generated for {next_day}'))

from django.core.management.base import BaseCommand
from bookings.kafka_consumer import run_all_consumers

class Command(BaseCommand):
    help = "Run all Kafka consumers with 3 parallel instances"

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting all Kafka consumers...")
        run_all_consumers()

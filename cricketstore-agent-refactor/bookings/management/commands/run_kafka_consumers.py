from django.core.management.base import BaseCommand

from bookings.kafka_consumer import run_all_consumers


class Command(BaseCommand):
    help = "Run Kafka consumers for booking confirmation events"

    def add_arguments(self, parser):
        parser.add_argument(
            "--instances",
            type=int,
            default=1,
            help="Number of booking/retry consumer instances to start",
        )

    def handle(self, *args, **options):
        instances = max(1, options["instances"])
        self.stdout.write(f"Starting Kafka consumers with {instances} booking instance(s)...")
        run_all_consumers(instances=instances)

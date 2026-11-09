from django.core.management.base import BaseCommand

from jobs.worker import run_worker


class Command(BaseCommand):
    help = "Run the durable job worker."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true", help="Process at most one job and exit.")

    def handle(self, *args, **options) -> None:
        run_worker(once=bool(options["once"]))

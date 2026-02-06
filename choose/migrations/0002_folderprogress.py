from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("choose", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FolderProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folder", models.CharField(max_length=512, unique=True)),
                ("last_classified_name", models.CharField(blank=True, default="", max_length=512)),
                ("last_classified_original", models.CharField(blank=True, default="", max_length=512)),
                ("keep_count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]

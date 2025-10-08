from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ExtractionJob',
            fields=[
                ('id', models.CharField(editable=False, max_length=32, primary_key=True, serialize=False)),
                ('params', models.JSONField()),
                ('output_dir', models.CharField(max_length=1024)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('done', 'Done'), ('error', 'Error')], default='pending', max_length=16)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('total_steps', models.PositiveIntegerField(default=0)),
                ('current_step', models.PositiveIntegerField(default=0)),
                ('total_frames', models.PositiveIntegerField(default=0)),
            ],
            options={'ordering': ('-created_at',)},
        ),
    ]
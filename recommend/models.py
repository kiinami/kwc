from django.db import models

class ImageFeature(models.Model):
    file_hash = models.CharField(max_length=64, unique=True, db_index=True)
    file_path = models.CharField(max_length=1024)
    feature_vector = models.BinaryField()  # pickled numpy array
    sharpness_score = models.FloatField()
    brightness_score = models.FloatField()
    file_size_bytes = models.BigIntegerField()
    resolution_width = models.IntegerField()
    resolution_height = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_path} ({self.file_hash[:8]})"

class LearnerModel(models.Model):
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    classifier_data = models.BinaryField()  # pickled sklearn model
    training_sample_count = models.IntegerField()
    accuracy_score = models.FloatField(null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"v{self.version} ({self.created_at.date()})"

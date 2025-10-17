import json
import os
import re
from datetime import timedelta

from django import forms

TIME_RANGE_RE = re.compile(r"^\d{2}:\d{2}:\d{2}-\d{2}:\d{2}:\d{2}$")


class ExtractStartForm(forms.Form):
    video = forms.CharField(
        label="Video file path",
        max_length=1024,
        widget=forms.TextInput(attrs={"placeholder": "/path/to/video.mp4"}),
    )
    title = forms.CharField(
        label="Title",
        max_length=256,
        widget=forms.TextInput(attrs={"placeholder": "Film title"}),
    )
    year = forms.IntegerField(
        label="Year",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "placeholder": "2025"}),
    )
    season = forms.IntegerField(
        label="Season",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "placeholder": "1"}),
    )
    episode = forms.CharField(
        label="Episode",
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"placeholder": "1"}),
    )

    # Transcode options removed

    # Backed by a hidden JSON string that the UI manages
    trim_intervals = forms.CharField(widget=forms.HiddenInput(), required=False)
    
    # Cover image URL from TMDB (optional)
    cover_image_url = forms.CharField(widget=forms.HiddenInput(), required=False)

    def clean(self):
        cleaned = super().clean()
        return cleaned

    def clean_video(self):
        path = (self.cleaned_data.get("video") or "").strip()
        if not path:
            raise forms.ValidationError("Please enter a video file path.")
        # Basic existence check; can be relaxed/removed if you prefer creating later
        if not os.path.isabs(path):
            raise forms.ValidationError("Please enter an absolute path.")
        # Existence check optional: comment out if you want to allow future path
        if not os.path.exists(path):
            raise forms.ValidationError("Path does not exist on server.")
        if not os.path.isfile(path):
            raise forms.ValidationError("Path must be a file.")
        return path

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Please enter a title.")
        return title

    def clean_episode(self):
        # Accept empty, numbers or arbitrary strings
        value = (self.cleaned_data.get("episode") or "").strip()
        return value

    def clean_trim_intervals(self):
        value = self.cleaned_data.get("trim_intervals")
        if not value:
            return []
        try:
            items = json.loads(value)
        except Exception:
            raise forms.ValidationError("Invalid trim intervals data.") from None
        if not isinstance(items, list):
            raise forms.ValidationError("Trim intervals must be a list.")

        def to_seconds(hms: str) -> int:
            h, m, s = map(int, hms.split(":"))
            return int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())

        normalized: list[str] = []
        for item in items:
            if not isinstance(item, str) or not TIME_RANGE_RE.match(item):
                raise forms.ValidationError("Intervals must be in HH:MM:SS-HH:MM:SS format.")
            start, end = item.split("-")
            if to_seconds(end) <= to_seconds(start):
                raise forms.ValidationError("Interval end must be after start.")
            normalized.append(item)
        return normalized

    def clean_cover_image_url(self):
        """Validate the cover image URL if provided."""
        url = (self.cleaned_data.get("cover_image_url") or "").strip()
        # Allow empty (optional field)
        if not url:
            return ""
        # Basic URL validation - should be an https URL
        if not url.startswith("https://"):
            raise forms.ValidationError("Cover image URL must be an HTTPS URL.")
        return url

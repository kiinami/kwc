import re

from django import forms


class ImportForm(forms.Form):
    target = forms.CharField(max_length=1024, label="Target folder (relative to the wallpaper root)")
    source = forms.CharField(max_length=1024, label="Source folder (relative to the import root)")
    regex = forms.CharField(
        max_length=1024,
        label="Filename regex",
        help_text="Must contain a named group: (?P<index>...) and may contain (?P<type>...).",
    )
    pick_all = forms.BooleanField(required=False, label="Mark imported images as picked")

    def clean_regex(self):
        value = self.cleaned_data["regex"]
        try:
            pattern = re.compile(value)
        except re.error as exc:
            raise forms.ValidationError(f"Invalid regex: {exc}") from exc
        if "index" not in pattern.groupindex:
            raise forms.ValidationError("Regex must have a named group 'index'.")
        return value

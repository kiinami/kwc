from django import forms


class FolderCreateForm(forms.Form):
    KIND_CHOICES = (("movie", "Movie"), ("series", "Series"), ("other", "Other"))

    kind = forms.ChoiceField(choices=KIND_CHOICES)
    title = forms.CharField(max_length=255)
    year = forms.IntegerField(required=False, min_value=1000, max_value=9999)
    tmdb_id = forms.IntegerField(required=False, min_value=1)
    copyright = forms.CharField(max_length=500, required=False)

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        year = cleaned.get("year")
        tmdb_id = cleaned.get("tmdb_id")
        if kind in {"movie", "series"}:
            if year is None:
                self.add_error("year", "Required for movies and series.")
            if tmdb_id is None:
                self.add_error("tmdb_id", "Required for movies and series.")
        elif year is not None or tmdb_id is not None:
            raise forms.ValidationError("Other folders do not take a year or TMDB id.")
        return cleaned


class SearchForm(forms.Form):
    kind = forms.ChoiceField(choices=FolderCreateForm.KIND_CHOICES, initial="movie")
    query = forms.CharField(max_length=255)
    year = forms.IntegerField(required=False, min_value=1000, max_value=9999)

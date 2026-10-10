from django import forms

from .models import StudentProject, StudentSkill


class StudentProjectForm(forms.ModelForm):
    class Meta:
        model = StudentProject
        fields = ("title", "description", "role", "started_on", "completed_on")
        widgets = {
            "title": forms.TextInput(attrs={"autocomplete": "off", "maxlength": 160}),
            "description": forms.Textarea(attrs={"rows": 5, "maxlength": 3000}),
            "role": forms.TextInput(attrs={"autocomplete": "off", "maxlength": 120}),
            "started_on": forms.DateInput(attrs={"type": "date"}),
            "completed_on": forms.DateInput(attrs={"type": "date"}),
        }


class StudentSkillForm(forms.ModelForm):
    class Meta:
        model = StudentSkill
        fields = ("name", "proficiency_label", "description")
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off", "maxlength": 100}),
            "proficiency_label": forms.TextInput(attrs={"autocomplete": "off", "maxlength": 40}),
            "description": forms.TextInput(attrs={"autocomplete": "off", "maxlength": 500}),
        }


class DevelopmentReviewForm(forms.Form):
    outcome = forms.ChoiceField(
        choices=(("approve", "Validar declaración"), ("observe", "Solicitar corrección")),
        widget=forms.RadioSelect,
        label="Decisión",
    )
    note = forms.CharField(
        label="Comentario para el estudiante",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Indica brevemente el criterio o ajuste necesario…"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("outcome") == "observe" and not cleaned.get("note", "").strip():
            self.add_error("note", "Explica qué información debe corregirse.")
        return cleaned

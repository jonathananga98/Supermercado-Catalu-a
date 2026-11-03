from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Correo Electrónico")

    class Meta:
        model = User
        fields = ['username', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Agregamos clases de Bootstrap a todos los campos automáticamente para que se vean bien
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control rounded-3'
            field.widget.attrs['placeholder'] = f'Ingrese su {field.label.lower()}'
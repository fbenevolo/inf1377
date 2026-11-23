from django import forms
from django.contrib.auth.hashers import check_password

from .models import Candidato, Empresa


class AutenticacaoForm(forms.Form):
    email = forms.EmailField()
    senha = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        senha = cleaned_data.get("senha")
        if not email or not senha:
            return cleaned_data

        candidato = Candidato.objects.filter(email=email).first()
        empresa = Empresa.objects.filter(email=email).first()
        conta = candidato or empresa
        if conta is None or not check_password(senha, conta.senha):
            raise forms.ValidationError("E-mail ou senha inválidos.")

        cleaned_data["conta"] = conta
        cleaned_data["tipo_conta"] = "candidato" if candidato else "empresa"
        return cleaned_data


class CandidatoCadastroForm(forms.ModelForm):
    senha = forms.CharField(widget=forms.PasswordInput, min_length=8)
    confirmar_senha = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Candidato
        fields = [
            "nome", "email", "cpf", "idade", "estado", "cep",
            "descricao", "senha", "confirmar_senha",
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("senha") != cleaned_data.get("confirmar_senha"):
            self.add_error("confirmar_senha", "As senhas não coincidem.")
        return cleaned_data


class EmpresaCadastroForm(forms.ModelForm):
    senha = forms.CharField(widget=forms.PasswordInput, min_length=8)
    confirmar_senha = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Empresa
        fields = [
            "nome", "email", "cnpj", "pais", "descricao",
            "senha", "confirmar_senha",
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("senha") != cleaned_data.get("confirmar_senha"):
            self.add_error("confirmar_senha", "As senhas não coincidem.")
        return cleaned_data


class CandidatoPerfilForm(CandidatoCadastroForm):
    senha = forms.CharField(widget=forms.PasswordInput, required=False, min_length=8)
    confirmar_senha = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta(CandidatoCadastroForm.Meta):
        fields = ["nome", "email", "cpf", "idade", "estado", "cep", "descricao", "senha", "confirmar_senha"]

    def clean(self):
        cleaned_data = super(CandidatoCadastroForm, self).clean()
        senha = cleaned_data.get("senha")
        confirmar = cleaned_data.get("confirmar_senha")
        if senha or confirmar:
            if senha != confirmar:
                self.add_error("confirmar_senha", "As senhas não coincidem.")
        return cleaned_data


class EmpresaPerfilForm(EmpresaCadastroForm):
    senha = forms.CharField(widget=forms.PasswordInput, required=False, min_length=8)
    confirmar_senha = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta(EmpresaCadastroForm.Meta):
        fields = ["nome", "email", "cnpj", "pais", "descricao", "senha", "confirmar_senha"]

    def clean(self):
        cleaned_data = super(EmpresaCadastroForm, self).clean()
        senha = cleaned_data.get("senha")
        confirmar = cleaned_data.get("confirmar_senha")
        if senha or confirmar:
            if senha != confirmar:
                self.add_error("confirmar_senha", "As senhas não coincidem.")
        return cleaned_data

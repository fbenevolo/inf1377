from functools import wraps

from django.contrib.auth.hashers import make_password
from django.contrib.auth import logout
from django.shortcuts import render
from django.shortcuts import redirect
from django.views.generic.edit import FormView

from .forms import (
    AutenticacaoForm,
    CandidatoCadastroForm,
    CandidatoPerfilForm,
    EmpresaCadastroForm,
    EmpresaPerfilForm,
)
from .models import Candidato, Empresa


def home(request):
    return render(request, "core/home.html")


def conta_autenticada(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("conta_id"):
            return redirect("core:login")
        return view(request, *args, **kwargs)
    return wrapper


@conta_autenticada
def vagas(request):
    return render(request, "core/vagas.html")


def login_view(request):
    form = AutenticacaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        conta = form.cleaned_data["conta"]
        request.session["conta_id"] = conta.pk
        request.session["tipo_conta"] = form.cleaned_data["tipo_conta"]
        return redirect("core:perfil")
    return render(request, "core/login.html", {"form": form})


def logout_view(request):
    logout(request)
    request.session.flush()
    return redirect("core:home")


def _conta_da_sessao(request):
    model = Candidato if request.session["tipo_conta"] == "candidato" else Empresa
    return model.objects.get(pk=request.session["conta_id"])


@conta_autenticada
def perfil(request):
    conta = _conta_da_sessao(request)
    form_class = CandidatoPerfilForm if isinstance(conta, Candidato) else EmpresaPerfilForm
    form = form_class(request.POST or None, instance=conta)
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        senha = form.cleaned_data.get("senha")
        if senha:
            objeto.senha = make_password(senha)
        objeto.save()
        return redirect("core:perfil")
    return render(request, "core/perfil.html", {"form": form, "conta": conta})


class CadastroView(FormView):
    template_name = "core/cadastro.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tipo"] = self.tipo
        return context

    def form_valid(self, form):
        objeto = form.save(commit=False)
        objeto.senha = make_password(form.cleaned_data["senha"])
        objeto.save()
        self.request.session["conta_id"] = objeto.pk
        self.request.session["tipo_conta"] = self.tipo
        return redirect("core:home")


class CadastroCandidatoView(CadastroView):
    form_class = CandidatoCadastroForm
    tipo = "candidato"


class CadastroEmpresaView(CadastroView):
    form_class = EmpresaCadastroForm
    tipo = "empresa"

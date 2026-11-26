from functools import wraps

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic.edit import FormView

from .forms import (
    AutenticacaoForm,
    CandidatoCadastroForm,
    CandidatoPerfilForm,
    EmpresaCadastroForm,
    EmpresaPerfilForm,
    VagaForm,
)
from .models import (
    AvaliacaoCandidato, Candidato, Empresa, HistoricoStatusVaga, MatchEmpresa,
    Swipe, SwipeEmpresa, Vaga,
)


def _criar_match_se_mutuo(candidato_id, empresa_id):
    curtida_candidato = SwipeEmpresa.objects.filter(
        candidato_id=candidato_id, empresa_id=empresa_id, vaga__isnull=True,
        direcao=Swipe.Direcao.CURTIR,
    ).exists()
    curtida_empresa = AvaliacaoCandidato.objects.filter(
        candidato_id=candidato_id, empresa_id=empresa_id,
        direcao=Swipe.Direcao.CURTIR,
    ).exists() or SwipeEmpresa.objects.filter(
        candidato_id=candidato_id, empresa_id=empresa_id, vaga__isnull=False,
        direcao=Swipe.Direcao.CURTIR,
    ).exists()
    if curtida_candidato and curtida_empresa:
        MatchEmpresa.objects.get_or_create(
            candidato_id=candidato_id, empresa_id=empresa_id,
        )


def _render_com_matches(request, template, context=None):
    context = dict(context or {})
    conta_id = request.session.get("conta_id")
    tipo_conta = request.session.get("tipo_conta")
    if not conta_id or tipo_conta not in ("candidato", "empresa"):
        return render(request, template, context)
    if tipo_conta == "candidato":
        pendentes = MatchEmpresa.objects.filter(
            candidato_id=conta_id, candidato_notificado=False,
        )
        campo = "candidato_notificado"
    else:
        pendentes = MatchEmpresa.objects.filter(
            empresa_id=conta_id, empresa_notificada=False,
        )
        campo = "empresa_notificada"
    with transaction.atomic():
        matches = list(pendentes.select_for_update().select_related("candidato", "empresa"))
        context["matches_novos"] = matches
        response = render(request, template, context)
        MatchEmpresa.objects.filter(pk__in=[match.pk for match in matches]).update(**{campo: True})
    return response


def home(request):
    return _render_com_matches(request, "core/home.html")


def cadastro_escolha(request):
    return render(request, "core/cadastro_escolha.html")


def conta_autenticada(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("conta_id"):
            return redirect("core:login")
        return view(request, *args, **kwargs)
    return wrapper


@conta_autenticada
def vagas(request):
    tipo_conta = request.session.get("tipo_conta")
    if tipo_conta == "empresa":
        vagas_empresa = Vaga.objects.filter(
            empresa_id=request.session["conta_id"],
        ).order_by("nome")
        if request.method == "POST":
            vaga_id = request.POST.get("vaga_id")
            vaga = vagas_empresa.filter(pk=vaga_id).first() if vaga_id else None
            candidato = Candidato.objects.filter(
                pk=request.POST.get("candidato_id"),
            ).first()
            direcao = request.POST.get("direcao")
            if candidato and direcao in Swipe.Direcao.values:
                if vaga or not vaga_id:
                    empresa_id = request.session["conta_id"]
                    with transaction.atomic():
                        Empresa.objects.select_for_update().get(pk=empresa_id)
                        if vaga:
                            SwipeEmpresa.objects.update_or_create(
                                candidato=candidato,
                                vaga=vaga,
                                defaults={"empresa_id": empresa_id, "direcao": direcao},
                            )
                        else:
                            AvaliacaoCandidato.objects.update_or_create(
                                candidato=candidato,
                                empresa_id=empresa_id,
                                defaults={"direcao": direcao},
                            )
                        if direcao == Swipe.Direcao.CURTIR:
                            _criar_match_se_mutuo(candidato.pk, empresa_id)
                    if vaga:
                        return redirect(f"{reverse('core:vagas')}?vaga_id={vaga.pk}")
            return redirect("core:vagas")

        vaga_id = request.GET.get("vaga_id")
        vaga = vagas_empresa.filter(pk=vaga_id).first() if vaga_id else None
        if vaga:
            avaliados = SwipeEmpresa.objects.filter(vaga=vaga).values("candidato_id")
        else:
            avaliados = AvaliacaoCandidato.objects.filter(
                empresa_id=request.session["conta_id"],
            ).values("candidato_id")
        candidato = (
            Candidato.objects.exclude(pk__in=avaliados)
            .order_by("nome")
            .first()
        )
        return _render_com_matches(
            request,
            "core/vagas.html",
            {
                "tipo_conta": tipo_conta,
                "vagas": vagas_empresa,
                "vaga": vaga,
                "candidato": candidato,
            },
        )

    if tipo_conta != "candidato":
        return render(request, "core/vagas.html", {"somente_candidato": True})

    candidato_id = request.session["conta_id"]
    if request.method == "POST":
        direcao = request.POST.get("direcao")
        empresa = Empresa.objects.filter(pk=request.POST.get("empresa_id")).first()
        if empresa and direcao in Swipe.Direcao.values:
            with transaction.atomic():
                Empresa.objects.select_for_update().get(pk=empresa.pk)
                SwipeEmpresa.objects.update_or_create(
                    candidato_id=candidato_id,
                    empresa=empresa,
                    vaga=None,
                    defaults={"direcao": direcao},
                )
                if direcao == Swipe.Direcao.CURTIR:
                    _criar_match_se_mutuo(candidato_id, empresa.pk)
        return redirect("core:vagas")

    empresa = (
        Empresa.objects.exclude(
            pk__in=SwipeEmpresa.objects.filter(
                candidato_id=candidato_id,
                vaga__isnull=True,
            ).values("empresa_id")
        )
        .order_by("nome")
        .first()
    )
    return _render_com_matches(
        request,
        "core/vagas.html",
        {
            "tipo_conta": tipo_conta, "empresa": empresa,
        },
    )


# ---------------------------------------------------------------------------
# UC04 · Gerenciar vagas
# ---------------------------------------------------------------------------

def empresa_autenticada(view):
    """Pré-condição do UC04: a empresa está autenticada."""
    @wraps(view)
    @conta_autenticada
    def wrapper(request, *args, **kwargs):
        if request.session.get("tipo_conta") != "empresa":
            messages.error(request, "Apenas empresas podem gerenciar vagas.")
            return redirect("core:home")
        return view(request, *args, **kwargs)
    return wrapper


def _vagas_da_empresa(request):
    status_mais_recente = HistoricoStatusVaga.objects.filter(
        vaga=OuterRef("pk"),
    ).order_by("-data_alteracao", "-pk").values("status")[:1]
    return Vaga.objects.filter(
        empresa_id=request.session["conta_id"],
    ).annotate(status_anotado=Subquery(status_mais_recente))


def _vaga_travada(request, pk):
    """Trava a vaga da empresa logada para que duas mudanças de status não se cruzem."""
    return get_object_or_404(
        Vaga.objects.select_for_update(), pk=pk, empresa_id=request.session["conta_id"],
    )


@empresa_autenticada
def minhas_vagas(request):
    """Passo 1: lista as vagas da empresa com o status atual de cada uma."""
    vagas_empresa = _vagas_da_empresa(request).order_by("-data_criacao", "nome")
    return render(request, "core/minhas_vagas.html", {"vagas": vagas_empresa})


@empresa_autenticada
def vaga_nova(request):
    """Passos 2 a 7: cria a vaga e registra o status Publicada no histórico."""
    empresa = Empresa.objects.get(pk=request.session["conta_id"])
    form = VagaForm(request.POST or None, empresa=empresa)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            vaga = form.save()
            vaga.alterar_status(HistoricoStatusVaga.Status.PUBLICADA)
        messages.success(request, f"Vaga “{vaga.nome}” publicada.")
        return redirect("core:minhas-vagas")
    return render(request, "core/vaga_form.html", {"form": form, "vaga": None})


@empresa_autenticada
def vaga_editar(request, pk):
    """[A1] Editar vaga: mesmo formulário, preenchido com os dados atuais."""
    vaga = get_object_or_404(_vagas_da_empresa(request), pk=pk)
    form = VagaForm(request.POST or None, instance=vaga, empresa=vaga.empresa)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Vaga “{vaga.nome}” atualizada.")
        return redirect("core:minhas-vagas")
    return render(request, "core/vaga_form.html", {"form": form, "vaga": vaga})


@require_POST
@empresa_autenticada
def vaga_alterar_status(request, pk):
    """[A2] Pausar ou reativar vaga."""
    acoes = {
        "pausar": HistoricoStatusVaga.Status.PAUSADA,
        "reativar": HistoricoStatusVaga.Status.PUBLICADA,
    }
    novo_status = acoes.get(request.POST.get("acao"))
    if novo_status is None:
        messages.error(request, "Ação inválida.")
        return redirect("core:minhas-vagas")
    with transaction.atomic():
        vaga = _vaga_travada(request, pk)
        try:
            vaga.alterar_status(novo_status)
        except ValidationError as erro:
            messages.error(request, erro.messages[0])
        else:
            messages.success(
                request, f"Vaga “{vaga.nome}” agora está {vaga.get_status_atual_display().lower()}.",
            )
    return redirect("core:minhas-vagas")


@empresa_autenticada
def vaga_encerrar(request, pk):
    """[A3] Encerrar vaga: pede confirmação; os matches existentes são mantidos."""
    vaga = get_object_or_404(_vagas_da_empresa(request), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            vaga = _vaga_travada(request, pk)
            try:
                vaga.alterar_status(HistoricoStatusVaga.Status.ENCERRADA)
            except ValidationError as erro:
                messages.error(request, erro.messages[0])
            else:
                messages.success(request, f"Vaga “{vaga.nome}” encerrada.")
        return redirect("core:minhas-vagas")
    return render(request, "core/vaga_encerrar.html", {"vaga": vaga})


def login_view(request):
    form = AutenticacaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        conta = form.cleaned_data["conta"]
        request.session["conta_id"] = conta.pk
        request.session["tipo_conta"] = form.cleaned_data["tipo_conta"]
        request.session["nome_conta"] = conta.nome
        return redirect("core:home")
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

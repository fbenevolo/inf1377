from functools import wraps

from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.contrib.auth import logout
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
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
    AvaliacaoCandidato,
    Candidato,
    Empresa,
    MatchEmpresa,
    StatusVaga,
    Swipe,
    SwipeEmpresa,
    Vaga,
)


def _criar_match_se_mutuo(candidato_id, empresa_id):
    # O candidato demonstra interesse na empresa ao curtir uma vaga dela no
    # feed (Swipe). SwipeEmpresa com vaga nula vem do antigo swipe em empresas
    # e continua valendo para dados já existentes.
    curtida_candidato = Swipe.objects.filter(
        candidato_id=candidato_id, vaga__empresa_id=empresa_id,
        direcao=Swipe.Direcao.CURTIR,
    ).exists() or SwipeEmpresa.objects.filter(
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


def apenas(tipo):
    """Restringe a view a um tipo de conta (exige login)."""
    def decorador(view):
        @conta_autenticada
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.session.get("tipo_conta") != tipo:
                return redirect("core:home")
            return view(request, *args, **kwargs)
        return wrapper
    return decorador


def _vaga_da_empresa(request, pk):
    return get_object_or_404(Vaga, pk=pk, empresa_id=request.session["conta_id"])


@conta_autenticada
def vagas(request):
    tipo_conta = request.session.get("tipo_conta")
    if tipo_conta == "empresa":
        vagas_empresa = Vaga.objects.publicadas().filter(
            empresa_id=request.session["conta_id"],
        ).order_by("titulo")
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
    # TODO(item 7): só exibir vagas de empresas com status Ativo (RN1).
    if request.method == "POST":
        direcao = request.POST.get("direcao")
        # Só vagas ainda publicadas recebem swipe; se foi pausada/encerrada
        # enquanto era exibida, o swipe é descartado (UC05 E2).
        vaga = Vaga.objects.publicadas().filter(pk=request.POST.get("vaga_id")).first()
        if vaga and direcao in Swipe.Direcao.values:
            with transaction.atomic():
                Empresa.objects.select_for_update().get(pk=vaga.empresa_id)
                # A vaga é avaliada uma única vez por candidato (RN2/RN3).
                _, criado = Swipe.objects.get_or_create(
                    candidato_id=candidato_id,
                    vaga=vaga,
                    defaults={"direcao": direcao},
                )
                if criado and direcao == Swipe.Direcao.CURTIR:
                    _criar_match_se_mutuo(candidato_id, vaga.empresa_id)
        return redirect("core:vagas")

    vaga = (
        Vaga.objects.publicadas()
        .exclude(swipes__candidato_id=candidato_id)
        .select_related("empresa")
        .order_by("data_criacao", "id")
        .first()
    )
    return _render_com_matches(
        request,
        "core/vagas.html",
        {"tipo_conta": tipo_conta, "vaga": vaga},
    )


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


# --- Painel da empresa: gerenciamento de vagas (UC04) -----------------------

ACOES_STATUS = {
    "pausar": StatusVaga.PAUSADA,
    "reativar": StatusVaga.PUBLICADA,
}


@apenas("empresa")
def painel_vagas(request):
    vagas_empresa = list(
        Vaga.objects.com_status()
        .filter(empresa_id=request.session["conta_id"])
        .order_by("-data_criacao", "-id")
    )
    for vaga in vagas_empresa:
        vaga.status_label = StatusVaga(vaga.status_anotado).label
    return render(request, "core/painel_vagas.html", {"vagas": vagas_empresa})


@apenas("empresa")
def vaga_criar(request):
    empresa = Empresa.objects.get(pk=request.session["conta_id"])
    form = VagaForm(request.POST or None, empresa=empresa)
    if request.method == "POST" and form.is_valid():
        Vaga.criar(empresa, **form.cleaned_data)
        messages.success(request, "Vaga criada e publicada.")
        return redirect("core:painel-vagas")
    return render(request, "core/vaga_form.html", {"form": form, "editando": False})


@apenas("empresa")
def vaga_editar(request, pk):
    vaga = _vaga_da_empresa(request, pk)
    if vaga.status_atual == StatusVaga.ENCERRADA:
        messages.error(request, "Vagas encerradas não podem ser editadas.")
        return redirect("core:painel-vagas")
    form = VagaForm(request.POST or None, instance=vaga, empresa=vaga.empresa)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Vaga atualizada.")
        return redirect("core:painel-vagas")
    return render(
        request,
        "core/vaga_form.html",
        {"form": form, "editando": True, "vaga": vaga},
    )


@apenas("empresa")
@require_POST
def vaga_alterar_status(request, pk):
    vaga = _vaga_da_empresa(request, pk)
    novo_status = ACOES_STATUS.get(request.POST.get("acao"))
    if novo_status is None:
        messages.error(request, "Ação inválida.")
    else:
        try:
            vaga.alterar_status(novo_status)
        except ValueError:
            messages.error(request, "Esta vaga não pode mudar para esse status.")
        else:
            messages.success(request, f"Vaga “{vaga.titulo}”: {novo_status.label.lower()}.")
    return redirect("core:painel-vagas")


@apenas("empresa")
def vaga_encerrar(request, pk):
    vaga = _vaga_da_empresa(request, pk)
    if request.method == "POST":
        try:
            vaga.alterar_status(StatusVaga.ENCERRADA)
        except ValueError:
            messages.error(request, "Esta vaga já está encerrada.")
        else:
            messages.success(request, f"Vaga “{vaga.titulo}” encerrada.")
        return redirect("core:painel-vagas")
    return render(request, "core/vaga_encerrar.html", {"vaga": vaga})

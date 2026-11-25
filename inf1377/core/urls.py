from django.urls import path

from .views import (
    CadastroCandidatoView,
    CadastroEmpresaView,
    home,
    cadastro_escolha,
    login_view,
    logout_view,
    painel_vagas,
    perfil,
    vaga_alterar_status,
    vaga_criar,
    vaga_editar,
    vaga_encerrar,
    vagas,
)

app_name = "core"

urlpatterns = [
    path("", home, name="home"),
    path("cadastro/", cadastro_escolha, name="cadastro"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("perfil/", perfil, name="perfil"),
    path("vagas/", vagas, name="vagas"),
    path("empresa/vagas/", painel_vagas, name="painel-vagas"),
    path("empresa/vagas/nova/", vaga_criar, name="vaga-criar"),
    path("empresa/vagas/<int:pk>/editar/", vaga_editar, name="vaga-editar"),
    path("empresa/vagas/<int:pk>/status/", vaga_alterar_status, name="vaga-status"),
    path("empresa/vagas/<int:pk>/encerrar/", vaga_encerrar, name="vaga-encerrar"),
    path("cadastro/candidato/", CadastroCandidatoView.as_view(), name="cadastro-candidato"),
    path("cadastro/empresa/", CadastroEmpresaView.as_view(), name="cadastro-empresa"),
]

from django.urls import path

from .views import (
    CadastroCandidatoView,
    CadastroEmpresaView,
    home,
    cadastro_escolha,
    login_view,
    logout_view,
    perfil,
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
    path("cadastro/candidato/", CadastroCandidatoView.as_view(), name="cadastro-candidato"),
    path("cadastro/empresa/", CadastroEmpresaView.as_view(), name="cadastro-empresa"),
]

from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse

from .models import AvaliacaoCandidato, Candidato, Empresa, MatchEmpresa, SwipeEmpresa, Vaga


class CadastroTests(TestCase):
    def test_pagina_inicial(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Encontre conexões que fazem sentido")
        self.assertContains(response, reverse("core:cadastro"))

    def test_escolhe_tipo_de_conta_antes_do_cadastro(self):
        response = self.client.get(reverse("core:cadastro"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sou candidato")
        self.assertContains(response, reverse("core:cadastro-candidato"))
        self.assertContains(response, "Sou empresa")
        self.assertContains(response, reverse("core:cadastro-empresa"))

    def test_cadastra_candidato_com_senha_protegida(self):
        response = self.client.post(reverse("core:cadastro-candidato"), {
            "nome": "Ana Silva",
            "email": "ana@example.com",
            "cpf": "123.456.789-00",
            "idade": 28,
            "estado": "RJ",
            "cep": "20000-000",
            "descricao": "Desenvolvedora",
            "senha": "senha-segura",
            "confirmar_senha": "senha-segura",
        })
        self.assertRedirects(response, reverse("core:home"))
        candidato = Candidato.objects.get(email="ana@example.com")
        self.assertTrue(check_password("senha-segura", candidato.senha))
        self.assertEqual(self.client.session["conta_id"], candidato.pk)

    def test_rejeita_senhas_diferentes(self):
        response = self.client.post(reverse("core:cadastro-empresa"), {
            "nome": "Acme",
            "email": "contato@acme.com",
            "cnpj": "12.345.678/0001-00",
            "pais": "Brasil",
            "descricao": "Empresa",
            "senha": "senha-segura",
            "confirmar_senha": "outra-senha",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Empresa.objects.count(), 0)

    def test_autentica_e_permite_editar_perfil(self):
        candidato = Candidato.objects.create(
            nome="Ana Silva", email="ana@example.com", cpf="12345678900",
            idade=28, estado="RJ", cep="20000000", senha=make_password("senha-segura"),
        )
        response = self.client.post(reverse("core:login"), {
            "email": candidato.email, "senha": "senha-segura",
        })
        self.assertRedirects(response, reverse("core:home"))
        response = self.client.post(reverse("core:perfil"), {
            "nome": "Ana Silva Atualizada", "email": candidato.email,
            "cpf": candidato.cpf, "idade": 29, "estado": "SP",
            "cep": candidato.cep, "descricao": "Nova descrição",
            "senha": "", "confirmar_senha": "",
        })
        self.assertRedirects(response, reverse("core:perfil"))
        candidato.refresh_from_db()
        self.assertEqual(candidato.nome, "Ana Silva Atualizada")
        self.assertEqual(candidato.estado, "SP")


class SwipeTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Acme",
            email="contato@acme.com",
            cnpj="12.345.678/0001-00",
            pais="Brasil",
            senha=make_password("senha-segura"),
        )
        self.candidato = Candidato.objects.create(
            nome="Ana Silva",
            email="ana@example.com",
            cpf="12345678900",
            idade=28,
            estado="RJ",
            cep="20000000",
            descricao="Desenvolvedora",
            senha=make_password("senha-segura"),
        )
        self.vaga = Vaga.objects.create(
            empresa=self.empresa,
            nome="Desenvolvedora",
            descricao="Desenvolvimento de software",
        )

    def autenticar_empresa(self):
        session = self.client.session
        session["conta_id"] = self.empresa.pk
        session["tipo_conta"] = "empresa"
        session["nome_conta"] = self.empresa.nome
        session.save()

    def test_empresa_avalia_candidatos_sem_vaga_independentemente_do_candidato(self):
        self.vaga.delete()
        session = self.client.session
        session["conta_id"] = self.candidato.pk
        session["tipo_conta"] = "candidato"
        session.save()
        self.client.post(reverse("core:vagas"), {
            "empresa_id": self.empresa.pk,
            "direcao": "curtir",
        })

        self.autenticar_empresa()
        response = self.client.get(reverse("core:vagas"))
        self.assertContains(response, self.candidato.nome)
        self.assertNotContains(response, "Cadastre uma vaga antes de avaliar candidatos.")

        response = self.client.post(reverse("core:vagas"), {
            "candidato_id": self.candidato.pk,
            "direcao": "recusar",
        })
        self.assertRedirects(response, reverse("core:vagas"))
        self.assertEqual(
            AvaliacaoCandidato.objects.get(
                candidato=self.candidato, empresa=self.empresa,
            ).direcao,
            "recusar",
        )
        self.assertContains(
            self.client.get(reverse("core:vagas")),
            "Não há novos candidatos para sua empresa.",
        )

        session = self.client.session
        session["conta_id"] = self.candidato.pk
        session["tipo_conta"] = "candidato"
        session.save()
        self.assertContains(
            self.client.get(reverse("core:vagas")),
            "Você já avaliou todas as empresas disponíveis.",
        )
        self.assertEqual(
            SwipeEmpresa.objects.get(
                candidato=self.candidato, empresa=self.empresa, vaga__isnull=True,
            ).direcao,
            "curtir",
        )

    def test_avaliacao_geral_e_independente_de_vagas_e_de_outras_empresas(self):
        self.autenticar_empresa()
        self.assertContains(self.client.get(reverse("core:vagas")), self.candidato.nome)
        self.client.post(reverse("core:vagas"), {
            "candidato_id": self.candidato.pk,
            "direcao": "curtir",
        })
        self.assertContains(
            self.client.get(reverse("core:vagas"), {"vaga_id": self.vaga.pk}),
            self.candidato.nome,
        )

        outra_empresa = Empresa.objects.create(
            nome="Outra", email="outra@example.com", cnpj="98.765.432/0001-10",
            pais="Brasil", senha=make_password("senha-segura"),
        )
        session = self.client.session
        session["conta_id"] = outra_empresa.pk
        session.save()
        self.assertContains(self.client.get(reverse("core:vagas")), self.candidato.nome)

    def test_avaliacao_geral_rejeita_direcao_invalida(self):
        self.vaga.delete()
        self.autenticar_empresa()
        self.client.post(reverse("core:vagas"), {
            "candidato_id": self.candidato.pk,
            "direcao": "invalida",
        })
        self.assertContains(self.client.get(reverse("core:vagas")), self.candidato.nome)

    def test_empresa_pode_deslizar_candidatos_no_contexto_de_uma_vaga(self):
        self.autenticar_empresa()
        segunda_vaga = Vaga.objects.create(
            empresa=self.empresa,
            nome="Analista",
            descricao="Análise de dados",
        )

        response = self.client.get(reverse("core:vagas"), {"vaga_id": segunda_vaga.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.candidato.nome)
        self.assertContains(response, segunda_vaga.nome)
        self.assertContains(response, "pointerdown")

        response = self.client.post(reverse("core:vagas"), {
            "vaga_id": segunda_vaga.pk,
            "candidato_id": self.candidato.pk,
            "direcao": "curtir",
        })
        self.assertRedirects(
            response,
            f"{reverse('core:vagas')}?vaga_id={segunda_vaga.pk}",
        )
        swipe = SwipeEmpresa.objects.get(candidato=self.candidato, vaga=segunda_vaga)
        self.assertEqual(swipe.empresa, self.empresa)
        self.assertEqual(swipe.direcao, "curtir")

        response = self.client.get(
            reverse("core:vagas"),
            {"vaga_id": segunda_vaga.pk},
        )
        self.assertContains(response, "Não há novos candidatos para esta vaga.")
        response = self.client.get(reverse("core:vagas"), {"vaga_id": self.vaga.pk})
        self.assertContains(response, self.candidato.nome)

    def test_empresa_nao_pode_deslizar_em_vaga_de_outra_empresa(self):
        outra_empresa = Empresa.objects.create(
            nome="Outra",
            email="outra@example.com",
            cnpj="98.765.432/0001-10",
            pais="Brasil",
            senha=make_password("senha-segura"),
        )
        vaga_alheia = Vaga.objects.create(
            empresa=outra_empresa,
            nome="Designer",
            descricao="Design",
        )
        self.autenticar_empresa()

        self.client.post(reverse("core:vagas"), {
            "vaga_id": vaga_alheia.pk,
            "candidato_id": self.candidato.pk,
            "direcao": "curtir",
        })

        self.assertFalse(SwipeEmpresa.objects.filter(candidato=self.candidato).exists())

    def test_empresa_pode_ter_varias_vagas(self):
        segunda_vaga = Vaga.objects.create(
            empresa=self.empresa,
            nome="Analista",
            descricao="Análise de dados",
        )

        self.assertEqual(self.empresa.vagas.count(), 2)
        self.assertEqual(segunda_vaga.empresa, self.empresa)

    def test_swipe_da_empresa_nao_consume_o_feed_de_empresas_do_candidato(self):
        SwipeEmpresa.objects.create(
            candidato=self.candidato,
            empresa=self.empresa,
            vaga=self.vaga,
            direcao="curtir",
        )
        session = self.client.session
        session["conta_id"] = self.candidato.pk
        session["tipo_conta"] = "candidato"
        session.save()

        response = self.client.get(reverse("core:vagas"))

        self.assertContains(response, self.empresa.nome)
        self.client.post(reverse("core:vagas"), {
            "empresa_id": self.empresa.pk,
            "direcao": "recusar",
        })
        self.assertEqual(
            SwipeEmpresa.objects.get(
                candidato=self.candidato, empresa=self.empresa, vaga=None,
            ).direcao,
            "recusar",
        )

    def test_candidato_ainda_pode_deslizar_empresas(self):
        session = self.client.session
        session["conta_id"] = self.candidato.pk
        session["tipo_conta"] = "candidato"
        session.save()

        dados_swipe = {
            "empresa_id": self.empresa.pk,
            "direcao": "curtir",
        }
        response = self.client.post(reverse("core:vagas"), dados_swipe)
        self.assertRedirects(response, reverse("core:vagas"))
        dados_swipe["direcao"] = "recusar"
        response = self.client.post(reverse("core:vagas"), dados_swipe)

        self.assertRedirects(response, reverse("core:vagas"))
        self.assertEqual(
            SwipeEmpresa.objects.filter(
                candidato=self.candidato,
                empresa=self.empresa,
                vaga__isnull=True,
            ).count(),
            1,
        )
        self.assertTrue(
            SwipeEmpresa.objects.filter(
                candidato=self.candidato,
                empresa=self.empresa,
                vaga__isnull=True,
                direcao="recusar",
            ).exists()
        )


class MatchEmpresaTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Acme", email="contato@acme.com", cnpj="12345678000100",
            pais="Brasil", senha=make_password("senha-segura"),
        )
        self.candidato = Candidato.objects.create(
            nome="Ana Silva", email="ana@example.com", cpf="12345678900",
            idade=28, estado="RJ", cep="20000000",
            senha=make_password("senha-segura"),
        )
        self.empresa_client = Client()
        self.candidato_client = Client()
        for client, conta, tipo in (
            (self.empresa_client, self.empresa, "empresa"),
            (self.candidato_client, self.candidato, "candidato"),
        ):
            session = client.session
            session["conta_id"] = conta.pk
            session["tipo_conta"] = tipo
            session.save()

    def avaliar_candidato(self, direcao="curtir", vaga=None, follow=False):
        dados = {"candidato_id": self.candidato.pk, "direcao": direcao}
        if vaga:
            dados["vaga_id"] = vaga.pk
        return self.empresa_client.post(reverse("core:vagas"), dados, follow=follow)

    def avaliar_empresa(self, direcao="curtir", follow=False):
        return self.candidato_client.post(reverse("core:vagas"), {
            "empresa_id": self.empresa.pk,
            "direcao": direcao,
        }, follow=follow)

    def test_match_notifica_candidato_e_empresa_ao_entrar_novamente(self):
        self.avaliar_candidato()
        self.assertNotContains(self.empresa_client.get(reverse("core:home")), "Deu match!")
        response = self.avaliar_empresa(follow=True)
        self.assertContains(response, "Deu match!")
        self.assertContains(response, self.empresa.nome)
        self.assertNotContains(self.candidato_client.get(reverse("core:home")), "Deu match!")

        self.empresa_client.get(reverse("core:logout"))
        response = self.empresa_client.post(reverse("core:login"), {
            "email": self.empresa.email, "senha": "senha-segura",
        }, follow=True)
        self.assertContains(response, "Deu match!")
        self.assertContains(response, self.candidato.nome)
        self.assertNotContains(self.empresa_client.get(reverse("core:home")), "Deu match!")

        self.avaliar_empresa()
        self.assertNotContains(self.candidato_client.get(reverse("core:vagas")), "Deu match!")
        self.assertNotContains(self.empresa_client.get(reverse("core:home")), "Deu match!")
        self.assertEqual(MatchEmpresa.objects.count(), 1)

    def test_match_tambem_funciona_quando_candidato_curte_primeiro(self):
        self.avaliar_empresa()
        response = self.avaliar_candidato(follow=True)
        self.assertContains(response, "Deu match!")
        self.assertContains(response, self.candidato.nome)
        response = self.candidato_client.get(reverse("core:home"))
        self.assertContains(response, "Deu match!")
        self.assertContains(response, self.empresa.nome)

    def test_recusa_nao_gera_match(self):
        self.avaliar_candidato(direcao="recusar")
        response = self.avaliar_empresa(follow=True)
        self.assertNotContains(response, "Deu match!")
        self.assertNotContains(self.empresa_client.get(reverse("core:home")), "Deu match!")
        self.assertFalse(MatchEmpresa.objects.exists())

    def test_like_de_outra_empresa_nao_gera_match(self):
        outra = Empresa.objects.create(
            nome="Outra", email="outra@example.com", cnpj="98765432000100",
            pais="Brasil", senha=make_password("senha-segura"),
        )
        self.avaliar_candidato()
        response = self.candidato_client.post(reverse("core:vagas"), {
            "empresa_id": outra.pk, "direcao": "curtir",
        }, follow=True)
        self.assertNotContains(response, "Deu match!")
        self.assertFalse(MatchEmpresa.objects.exists())

    def test_candidato_que_recusa_nao_gera_match(self):
        self.avaliar_empresa(direcao="recusar")
        response = self.avaliar_candidato(follow=True)
        self.assertNotContains(response, "Deu match!")
        self.assertFalse(MatchEmpresa.objects.exists())

    def test_like_da_empresa_em_vaga_tambem_gera_match(self):
        vaga = Vaga.objects.create(
            empresa=self.empresa, nome="Desenvolvedor", descricao="Desenvolvimento",
        )
        self.avaliar_candidato(vaga=vaga)
        response = self.avaliar_empresa(follow=True)
        self.assertContains(response, "Deu match!")
        self.assertContains(response, self.empresa.nome)

    def test_migracao_reconhece_curtidas_mutuas_existentes(self):
        SwipeEmpresa.objects.create(
            candidato=self.candidato, empresa=self.empresa, direcao="curtir",
        )
        AvaliacaoCandidato.objects.create(
            candidato=self.candidato, empresa=self.empresa, direcao="curtir",
        )
        migracao = import_module("core.migrations.0009_matchempresa")
        schema_editor = SimpleNamespace(connection=connection)
        migracao.criar_matches_existentes(apps, schema_editor)
        migracao.criar_matches_existentes(apps, schema_editor)

        self.assertEqual(MatchEmpresa.objects.count(), 1)
        self.assertContains(self.candidato_client.get(reverse("core:home")), "Deu match!")
        self.assertContains(self.empresa_client.get(reverse("core:home")), "Deu match!")

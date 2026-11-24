from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.urls import reverse

from .models import Candidato, Empresa, SwipeEmpresa, Vaga


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
        self.assertRedirects(response, reverse("core:perfil"))
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

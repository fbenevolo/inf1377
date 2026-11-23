from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.urls import reverse

from .models import Candidato, Empresa


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

from django.contrib.auth.hashers import check_password
from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    Candidato,
    Empresa,
    HistoricoStatusVaga,
    StatusVaga,
    Swipe,
    SwipeEmpresa,
    Vaga,
)


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
        self.vaga = Vaga.criar(
            self.empresa,
            titulo="Desenvolvedora",
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
        segunda_vaga = Vaga.criar(
            self.empresa,
            titulo="Analista",
            descricao="Análise de dados",
        )

        response = self.client.get(reverse("core:vagas"), {"vaga_id": segunda_vaga.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.candidato.nome)
        self.assertContains(response, segunda_vaga.titulo)
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
        vaga_alheia = Vaga.criar(
            outra_empresa,
            titulo="Designer",
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
        segunda_vaga = Vaga.criar(
            self.empresa,
            titulo="Analista",
            descricao="Análise de dados",
        )

        self.assertEqual(self.empresa.vagas.count(), 2)
        self.assertEqual(segunda_vaga.empresa, self.empresa)


class BaseContaTests(TestCase):
    """Cria duas empresas e um candidato, com helper de sessão."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nome="Acme", email="contato@acme.com", cnpj="12.345.678/0001-00",
            pais="Brasil", senha=make_password("senha-segura"),
        )
        self.outra_empresa = Empresa.objects.create(
            nome="Outra", email="outra@example.com", cnpj="98.765.432/0001-10",
            pais="Brasil", senha=make_password("senha-segura"),
        )
        self.candidato = Candidato.objects.create(
            nome="Ana Silva", email="ana@example.com", cpf="12345678900",
            idade=28, estado="RJ", cep="20000000", senha=make_password("senha-segura"),
        )

    def entrar(self, conta, tipo):
        session = self.client.session
        session["conta_id"] = conta.pk
        session["tipo_conta"] = tipo
        session["nome_conta"] = conta.nome
        session.save()


class PainelVagasTests(BaseContaTests):
    def setUp(self):
        super().setUp()
        self.entrar(self.empresa, "empresa")
        self.dados = {
            "titulo": "Backend Python", "descricao": "API em Django",
            "salario": "8000.00", "modalidade": "remoto", "endereco": "Rio de Janeiro",
        }

    def test_criar_vaga_registra_status_publicada_no_historico(self):
        response = self.client.post(reverse("core:vaga-criar"), self.dados)
        self.assertRedirects(response, reverse("core:painel-vagas"))
        vaga = Vaga.objects.get(titulo="Backend Python")
        self.assertEqual(vaga.empresa, self.empresa)
        self.assertEqual(vaga.status_atual, StatusVaga.PUBLICADA)
        self.assertEqual(vaga.historico_status.count(), 1)

    def test_painel_lista_somente_vagas_da_empresa_com_status(self):
        Vaga.criar(self.empresa, titulo="Minha vaga", descricao="x")
        Vaga.criar(self.outra_empresa, titulo="Vaga alheia", descricao="x")
        response = self.client.get(reverse("core:painel-vagas"))
        self.assertContains(response, "Minha vaga")
        self.assertContains(response, "Publicada")
        self.assertNotContains(response, "Vaga alheia")

    def test_painel_sem_vagas_convida_a_criar(self):
        response = self.client.get(reverse("core:painel-vagas"))
        self.assertContains(response, "ainda não tem vagas")

    def test_editar_vaga(self):
        vaga = Vaga.criar(self.empresa, titulo="Antigo", descricao="x")
        self.dados["titulo"] = "Novo título"
        response = self.client.post(reverse("core:vaga-editar", args=[vaga.pk]), self.dados)
        self.assertRedirects(response, reverse("core:painel-vagas"))
        vaga.refresh_from_db()
        self.assertEqual(vaga.titulo, "Novo título")
        self.assertEqual(vaga.historico_status.count(), 1)

    def test_pausar_e_reativar_registram_historico(self):
        vaga = Vaga.criar(self.empresa, titulo="V", descricao="x")
        url = reverse("core:vaga-status", args=[vaga.pk])
        self.client.post(url, {"acao": "pausar"})
        self.assertEqual(vaga.status_atual, StatusVaga.PAUSADA)
        self.client.post(url, {"acao": "reativar"})
        self.assertEqual(vaga.status_atual, StatusVaga.PUBLICADA)
        self.assertEqual(
            list(vaga.historico_status.order_by("id").values_list("status", flat=True)),
            ["publicada", "pausada", "publicada"],
        )

    def test_encerrar_exige_confirmacao(self):
        vaga = Vaga.criar(self.empresa, titulo="V", descricao="x")
        url = reverse("core:vaga-encerrar", args=[vaga.pk])
        response = self.client.get(url)
        self.assertContains(response, "não poderá ser reativada")
        self.assertEqual(vaga.status_atual, StatusVaga.PUBLICADA)
        self.client.post(url)
        self.assertEqual(vaga.status_atual, StatusVaga.ENCERRADA)

    def test_vaga_encerrada_nao_reativa_nem_edita(self):
        vaga = Vaga.criar(self.empresa, titulo="V", descricao="x")
        vaga.alterar_status(StatusVaga.ENCERRADA)
        self.client.post(reverse("core:vaga-status", args=[vaga.pk]), {"acao": "reativar"})
        self.assertEqual(vaga.status_atual, StatusVaga.ENCERRADA)
        response = self.client.get(reverse("core:vaga-editar", args=[vaga.pk]))
        self.assertRedirects(response, reverse("core:painel-vagas"))
        with self.assertRaises(ValueError):
            vaga.alterar_status(StatusVaga.PUBLICADA)

    def test_status_atual_usa_o_registro_mais_recente_mesmo_com_mesmo_timestamp(self):
        vaga = Vaga.criar(self.empresa, titulo="V", descricao="x")
        vaga.alterar_status(StatusVaga.PAUSADA)
        instante = vaga.historico_status.first().data_alteracao
        HistoricoStatusVaga.objects.filter(vaga=vaga).update(data_alteracao=instante)
        self.assertEqual(vaga.status_atual, StatusVaga.PAUSADA)
        self.assertFalse(Vaga.objects.publicadas().filter(pk=vaga.pk).exists())

    def test_empresa_nao_altera_vaga_de_outra(self):
        alheia = Vaga.criar(self.outra_empresa, titulo="Alheia", descricao="x")
        self.assertEqual(self.client.get(reverse("core:vaga-editar", args=[alheia.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("core:vaga-encerrar", args=[alheia.pk])).status_code, 404)
        response = self.client.post(reverse("core:vaga-status", args=[alheia.pk]), {"acao": "pausar"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(alheia.status_atual, StatusVaga.PUBLICADA)

    def test_visitante_e_candidato_nao_acessam_o_painel(self):
        self.assertRedirects(Client().get(reverse("core:painel-vagas")), reverse("core:login"))
        self.entrar(self.candidato, "candidato")
        self.assertRedirects(self.client.get(reverse("core:painel-vagas")), reverse("core:home"))
        self.client.post(reverse("core:vaga-criar"), self.dados)
        self.assertFalse(Vaga.objects.filter(titulo="Backend Python").exists())

    def test_titulo_duplicado_na_empresa_gera_erro_de_formulario(self):
        Vaga.criar(self.empresa, titulo="Backend Python", descricao="x")
        response = self.client.post(reverse("core:vaga-criar"), self.dados)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "já possui uma vaga com este título")
        self.assertEqual(Vaga.objects.filter(titulo="Backend Python").count(), 1)

    def test_outra_empresa_pode_usar_o_mesmo_titulo(self):
        Vaga.criar(self.outra_empresa, titulo="Backend Python", descricao="x")
        response = self.client.post(reverse("core:vaga-criar"), self.dados)
        self.assertRedirects(response, reverse("core:painel-vagas"))

    def test_salario_negativo_e_rejeitado(self):
        self.dados["salario"] = "-1"
        response = self.client.post(reverse("core:vaga-criar"), self.dados)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vaga.objects.exists())


class FeedVagasTests(BaseContaTests):
    def setUp(self):
        super().setUp()
        self.vaga = Vaga.criar(
            self.empresa, titulo="Dev Backend", descricao="Construir APIs",
            salario="9500.00", modalidade=Vaga.Modalidade.HIBRIDO, endereco="Av. Paulista, SP",
        )
        self.entrar(self.candidato, "candidato")

    def swipe(self, vaga, direcao="curtir"):
        return self.client.post(reverse("core:vagas"), {"vaga_id": vaga.pk, "direcao": direcao})

    def test_feed_mostra_dados_da_vaga(self):
        response = self.client.get(reverse("core:vagas"))
        for texto in ["Dev Backend", "Acme", "Construir APIs", "9500,00", "Híbrido", "Av. Paulista, SP"]:
            self.assertContains(response, texto)

    def test_feed_mostra_salario_a_combinar(self):
        Vaga.objects.filter(pk=self.vaga.pk).update(salario=None)
        self.assertContains(self.client.get(reverse("core:vagas")), "Salário a combinar")

    def test_like_e_dislike_registram_swipe_e_avancam_o_feed(self):
        outra = Vaga.criar(self.empresa, titulo="Outra vaga", descricao="x")
        self.assertRedirects(self.swipe(self.vaga, "curtir"), reverse("core:vagas"))
        self.assertEqual(Swipe.objects.get(candidato=self.candidato, vaga=self.vaga).direcao, "curtir")
        response = self.client.get(reverse("core:vagas"))
        self.assertContains(response, "Outra vaga")
        self.assertNotContains(response, "Dev Backend")
        self.swipe(outra, "recusar")
        self.assertEqual(Swipe.objects.get(vaga=outra).direcao, "recusar")
        self.assertContains(self.client.get(reverse("core:vagas")), "Sem novas vagas por enquanto")

    def test_vaga_so_e_avaliada_uma_vez(self):
        self.swipe(self.vaga, "recusar")
        self.swipe(self.vaga, "curtir")
        self.assertEqual(Swipe.objects.filter(vaga=self.vaga).count(), 1)
        self.assertEqual(Swipe.objects.get(vaga=self.vaga).direcao, "recusar")

    def test_vagas_pausadas_e_encerradas_nao_aparecem(self):
        pausada = Vaga.criar(self.empresa, titulo="Pausada", descricao="x")
        pausada.alterar_status(StatusVaga.PAUSADA)
        encerrada = Vaga.criar(self.empresa, titulo="Encerrada", descricao="x")
        encerrada.alterar_status(StatusVaga.ENCERRADA)
        self.swipe(self.vaga)
        self.assertContains(self.client.get(reverse("core:vagas")), "Sem novas vagas")

    def test_swipe_em_vaga_pausada_e_descartado(self):
        self.vaga.alterar_status(StatusVaga.PAUSADA)
        self.swipe(self.vaga)
        self.assertFalse(Swipe.objects.exists())

    def test_direcao_invalida_e_ignorada(self):
        self.swipe(self.vaga, "talvez")
        self.assertFalse(Swipe.objects.exists())

    def test_empresa_so_ve_vagas_publicadas_no_select_de_avaliacao(self):
        pausada = Vaga.criar(self.empresa, titulo="Vaga pausada", descricao="x")
        pausada.alterar_status(StatusVaga.PAUSADA)
        self.entrar(self.empresa, "empresa")
        response = self.client.get(reverse("core:vagas"))
        self.assertContains(response, "Dev Backend")
        self.assertNotContains(response, "Vaga pausada")

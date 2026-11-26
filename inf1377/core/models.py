from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import OuterRef, Subquery


class Competencia(models.Model):
    """Habilidade que pode ser informada por candidatos e exigida por vagas."""

    nome = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "competência"
        verbose_name_plural = "competências"

    def __str__(self):
        return self.nome


class Candidato(models.Model):
    nome = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    cpf = models.CharField(max_length=14, unique=True)
    idade = models.PositiveSmallIntegerField(validators=[MinValueValidator(16)])
    estado = models.CharField(max_length=2)
    cep = models.CharField(max_length=9)
    descricao = models.TextField(blank=True)
    senha = models.CharField(max_length=128)
    competencias = models.ManyToManyField(
        Competencia,
        related_name="candidatos",
        blank=True,
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "candidato"
        verbose_name_plural = "candidatos"

    def __str__(self):
        return self.nome


class Empresa(models.Model):
    nome = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    cnpj = models.CharField(max_length=18, unique=True)
    pais = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    senha = models.CharField(max_length=128)

    class Meta:
        ordering = ["nome"]
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self):
        return self.nome


class StatusVaga(models.TextChoices):
    PUBLICADA = "publicada", "Publicada"
    PAUSADA = "pausada", "Pausada"
    ENCERRADA = "encerrada", "Encerrada"


# Transições permitidas (RN3: vaga encerrada não é reativada).
TRANSICOES_STATUS_VAGA = {
    StatusVaga.PUBLICADA: {StatusVaga.PAUSADA, StatusVaga.ENCERRADA},
    StatusVaga.PAUSADA: {StatusVaga.PUBLICADA, StatusVaga.ENCERRADA},
    StatusVaga.ENCERRADA: set(),
}


class VagaQuerySet(models.QuerySet):
    def com_status(self):
        """Anota `status_atual` com o registro mais recente do histórico."""
        mais_recente = HistoricoStatusVaga.objects.filter(
            vaga=OuterRef("pk"),
        ).order_by("-data_alteracao", "-id")
        return self.annotate(status_anotado=Subquery(mais_recente.values("status")[:1]))

    def publicadas(self):
        return self.com_status().filter(status_anotado=StatusVaga.PUBLICADA)


class Vaga(models.Model):
    class Modalidade(models.TextChoices):
        REMOTO = "remoto", "Remoto"
        HIBRIDO = "hibrido", "Híbrido"
        PRESENCIAL = "presencial", "Presencial"

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="vagas",
    )
    titulo = models.CharField(max_length=150)
    descricao = models.TextField()
    salario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    endereco = models.CharField(max_length=255, blank=True)
    modalidade = models.CharField(
        max_length=10,
        choices=Modalidade.choices,
        default=Modalidade.PRESENCIAL,
    )
    data_criacao = models.DateTimeField(auto_now_add=True)
    competencias = models.ManyToManyField(
        Competencia,
        related_name="vagas",
        blank=True,
    )

    objects = VagaQuerySet.as_manager()

    class Meta:
        ordering = ["empresa__nome", "titulo"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "titulo"],
                name="unique_vaga_por_empresa",
            )
        ]
        verbose_name = "vaga"
        verbose_name_plural = "vagas"

    def __str__(self):
        return f"{self.titulo} - {self.empresa.nome}"

    @classmethod
    def criar(cls, empresa, **dados):
        """Cria a vaga já publicada e registra o status no histórico (RN2)."""
        with transaction.atomic():
            vaga = cls.objects.create(empresa=empresa, **dados)
            HistoricoStatusVaga.objects.create(vaga=vaga, status=StatusVaga.PUBLICADA)
        return vaga

    @property
    def status_atual(self):
        registro = self.historico_status.first()
        return registro.status if registro else None

    @property
    def status_atual_display(self):
        return StatusVaga(self.status_atual).label if self.status_atual else ""

    def pode_ir_para(self, novo_status):
        atual = self.status_atual
        return atual is not None and novo_status in TRANSICOES_STATUS_VAGA[StatusVaga(atual)]

    def alterar_status(self, novo_status):
        with transaction.atomic():
            if not self.pode_ir_para(novo_status):
                raise ValueError(
                    f"Transição inválida: {self.status_atual} -> {novo_status}."
                )
            return HistoricoStatusVaga.objects.create(vaga=self, status=novo_status)


class HistoricoStatusVaga(models.Model):
    vaga = models.ForeignKey(
        Vaga,
        on_delete=models.CASCADE,
        related_name="historico_status",
    )
    status = models.CharField(max_length=10, choices=StatusVaga.choices)
    data_alteracao = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_alteracao", "-id"]
        verbose_name = "histórico de status da vaga"
        verbose_name_plural = "histórico de status das vagas"

    def __str__(self):
        return f"{self.vaga}: {self.get_status_display()}"


class Swipe(models.Model):
    class Direcao(models.TextChoices):
        CURTIR = "curtir", "Curtir"
        RECUSAR = "recusar", "Recusar"

    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="swipes",
    )
    vaga = models.ForeignKey(
        Vaga,
        on_delete=models.CASCADE,
        related_name="swipes",
    )
    direcao = models.CharField(max_length=7, choices=Direcao.choices)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidato", "vaga"],
                name="unique_swipe_por_candidato_e_vaga",
            )
        ]

    def __str__(self):
        return f"{self.candidato} - {self.vaga}: {self.get_direcao_display()}"


class SwipeEmpresa(models.Model):
    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="swipes_empresa",
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="swipes",
    )
    vaga = models.ForeignKey(
        Vaga,
        on_delete=models.CASCADE,
        related_name="swipes_empresa",
        null=True,
        blank=True,
    )
    direcao = models.CharField(max_length=7, choices=Swipe.Direcao.choices)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidato", "empresa"],
                condition=models.Q(vaga__isnull=True),
                name="unique_swipe_candidato_empresa",
            ),
            models.UniqueConstraint(
                fields=["candidato", "vaga"],
                name="unique_swipe_empresa_por_candidato_e_vaga",
            )
        ]

    def __str__(self):
        return f"{self.candidato} - {self.empresa}: {self.get_direcao_display()}"


class AvaliacaoCandidato(models.Model):
    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="avaliacoes_empresas",
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="avaliacoes_candidatos",
    )
    direcao = models.CharField(max_length=7, choices=Swipe.Direcao.choices)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["candidato", "empresa"],
                name="unique_avaliacao_candidato_empresa",
            ),
        ]

    def __str__(self):
        return f"{self.empresa} - {self.candidato}: {self.get_direcao_display()}"


class MatchEmpresa(models.Model):
    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="matches_empresas",
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="matches_candidatos",
    )
    candidato_notificado = models.BooleanField(default=False)
    empresa_notificada = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidato", "empresa"],
                name="unique_match_candidato_empresa",
            ),
        ]

    def __str__(self):
        return f"Match: {self.candidato} - {self.empresa}"


class Match(models.Model):
    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    vaga = models.ForeignKey(
        Vaga,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidato", "vaga"],
                name="unique_match_por_candidato_e_vaga",
            )
        ]

    def __str__(self):
        return f"Match: {self.candidato} - {self.vaga}"


class Conversa(models.Model):
    match = models.OneToOneField(
        Match,
        on_delete=models.CASCADE,
        related_name="conversa",
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "conversa"
        verbose_name_plural = "conversas"

    def __str__(self):
        return f"Conversa do {self.match}"


class Mensagem(models.Model):
    class TipoRemetente(models.TextChoices):
        CANDIDATO = "candidato", "Candidato"
        EMPRESA = "empresa", "Empresa"

    conversa = models.ForeignKey(
        Conversa,
        on_delete=models.CASCADE,
        related_name="mensagens",
    )
    tipo_remetente = models.CharField(max_length=9, choices=TipoRemetente.choices)
    remetente_candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="mensagens_enviadas",
        null=True,
        blank=True,
    )
    remetente_empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="mensagens_enviadas",
        null=True,
        blank=True,
    )
    conteudo = models.TextField()
    enviada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["enviada_em"]
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"

    def __str__(self):
        return f"Mensagem em {self.conversa} ({self.enviada_em:%Y-%m-%d %H:%M})"

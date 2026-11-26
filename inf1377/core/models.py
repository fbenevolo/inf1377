from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


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
    nome = models.CharField("título", max_length=150)
    descricao = models.TextField("descrição")
    salario = models.DecimalField(
        "salário",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    modalidade = models.CharField(
        max_length=10,
        choices=Modalidade.choices,
        default=Modalidade.PRESENCIAL,
    )
    endereco = models.CharField("endereço", max_length=255, blank=True)
    data_criacao = models.DateTimeField(default=timezone.now, editable=False)
    competencias = models.ManyToManyField(
        Competencia,
        related_name="vagas",
        blank=True,
    )

    # UC04: transições permitidas entre status (RN3: Encerrada é final).
    TRANSICOES_STATUS = {
        None: {"publicada"},
        "publicada": {"pausada", "encerrada"},
        "pausada": {"publicada", "encerrada"},
        "encerrada": set(),
    }

    @property
    def status_atual(self):
        """RN2: o status atual é o registro mais recente do histórico."""
        if hasattr(self, "status_anotado"):
            return self.status_anotado
        ultimo = self.historico_status.order_by("-data_alteracao", "-pk").first()
        return ultimo.status if ultimo else None

    def get_status_atual_display(self):
        status = self.status_atual
        return HistoricoStatusVaga.Status(status).label if status else "Sem status"

    def alterar_status(self, novo_status):
        """Registra uma mudança de status no histórico (UC04 · RN2/RN3)."""
        atual = self.status_atual
        if novo_status not in self.TRANSICOES_STATUS.get(atual, set()):
            raise ValidationError(
                f"Não é possível mudar a vaga de "
                f"“{self.get_status_atual_display()}” para "
                f"“{HistoricoStatusVaga.Status(novo_status).label}”."
            )
        registro = HistoricoStatusVaga.objects.create(vaga=self, status=novo_status)
        # Descarta o status anotado na consulta para que a próxima leitura venha do histórico.
        self.__dict__.pop("status_anotado", None)
        return registro

    class Meta:
        ordering = ["empresa__nome", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nome"],
                name="unique_vaga_por_empresa",
            )
        ]
        verbose_name = "vaga"
        verbose_name_plural = "vagas"

    def __str__(self):
        return f"{self.nome} - {self.empresa.nome}"


class HistoricoStatusVaga(models.Model):
    """Classe associativa entre Vaga e StatusVaga (diagrama de classes)."""

    class Status(models.TextChoices):
        PUBLICADA = "publicada", "Publicada"
        PAUSADA = "pausada", "Pausada"
        ENCERRADA = "encerrada", "Encerrada"

    vaga = models.ForeignKey(
        Vaga,
        on_delete=models.CASCADE,
        related_name="historico_status",
    )
    status = models.CharField(max_length=9, choices=Status.choices)
    data_alteracao = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-data_alteracao", "-pk"]
        verbose_name = "histórico de status da vaga"
        verbose_name_plural = "históricos de status das vagas"

    def __str__(self):
        return f"{self.vaga}: {self.get_status_display()} ({self.data_alteracao:%d/%m/%Y %H:%M})"


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

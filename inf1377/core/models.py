from django.core.validators import MinValueValidator
from django.db import models


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
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="vagas",
    )
    nome = models.CharField(max_length=150)
    descricao = models.TextField()
    competencias = models.ManyToManyField(
        Competencia,
        related_name="vagas",
        blank=True,
    )

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

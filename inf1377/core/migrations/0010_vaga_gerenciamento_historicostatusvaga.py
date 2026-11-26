# UC04 · Gerenciar vagas: novos campos da vaga e histórico de status.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def publicar_vagas_existentes(apps, schema_editor):
    """Vagas criadas antes do histórico passam a ter status Publicada."""
    db = schema_editor.connection.alias
    vaga = apps.get_model("core", "Vaga")
    historico = apps.get_model("core", "HistoricoStatusVaga")
    historico.objects.using(db).bulk_create(
        historico(vaga_id=vaga_id, status="publicada")
        for vaga_id in vaga.objects.using(db).values_list("pk", flat=True).iterator()
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_matchempresa"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vaga",
            name="nome",
            field=models.CharField(max_length=150, verbose_name="título"),
        ),
        migrations.AlterField(
            model_name="vaga",
            name="descricao",
            field=models.TextField(verbose_name="descrição"),
        ),
        migrations.AddField(
            model_name="vaga",
            name="salario",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="salário",
            ),
        ),
        migrations.AddField(
            model_name="vaga",
            name="modalidade",
            field=models.CharField(
                choices=[
                    ("remoto", "Remoto"),
                    ("hibrido", "Híbrido"),
                    ("presencial", "Presencial"),
                ],
                default="presencial",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="vaga",
            name="endereco",
            field=models.CharField(blank=True, max_length=255, verbose_name="endereço"),
        ),
        migrations.AddField(
            model_name="vaga",
            name="data_criacao",
            field=models.DateTimeField(default=django.utils.timezone.now, editable=False),
        ),
        migrations.CreateModel(
            name="HistoricoStatusVaga",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("publicada", "Publicada"),
                            ("pausada", "Pausada"),
                            ("encerrada", "Encerrada"),
                        ],
                        max_length=9,
                    ),
                ),
                ("data_alteracao", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "vaga",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historico_status",
                        to="core.vaga",
                    ),
                ),
            ],
            options={
                "verbose_name": "histórico de status da vaga",
                "verbose_name_plural": "históricos de status das vagas",
                "ordering": ["-data_alteracao", "-pk"],
            },
        ),
        migrations.RunPython(publicar_vagas_existentes, migrations.RunPython.noop),
    ]

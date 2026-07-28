# Generated migration to add insured_amount to SupplierDocument
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0005_supplierdocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='supplierdocument',
            name='insured_amount',
            field=models.DecimalField(blank=True, null=True, max_digits=15, decimal_places=2),
        ),
    ]

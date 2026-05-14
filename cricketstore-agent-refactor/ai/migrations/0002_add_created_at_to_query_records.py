# Generated manually for the copied refactor project.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="queryrecordground",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=None),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="queryrecordproduct",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=None),
            preserve_default=False,
        ),
    ]

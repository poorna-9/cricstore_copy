from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_tournamentsession_created_at'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='slots',
            unique_together={('ground', 'date', 'starttime', 'endtime')},
        ),
    ]

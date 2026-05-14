from django_elasticsearch_dsl import Document, Index, fields
from django_elasticsearch_dsl.registries import registry
from .models import Ground

bookings_index = Index('bookings-grounds')
bookings_index.settings(
    number_of_shards=1,
    number_of_replicas=0
)

@registry.register_document
class GroundDocument(Document):
    class Index:
        name = 'bookings-grounds'
        settings = {'number_of_shards': 1, 'number_of_replicas': 0}

    class Django:
        model = Ground
        fields = [
            'id',
            'name',
            'address',
            'price',
        ]

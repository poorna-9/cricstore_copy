from django_elasticsearch_dsl import Document, Index, fields
from django_elasticsearch_dsl.registries import registry
from .models import Product

store_index = Index('store-products')
store_index.settings(number_of_shards=1, number_of_replicas=0)

@registry.register_document
class ProductDocument(Document):
    class Index:
        name = 'store-products'
        settings = {'number_of_shards': 1, 'number_of_replicas': 0}

    class Django:
        model = Product
        fields = [
            'id',
            'name',
            'description',
            'price',
            'colour',
            'manufacturer',
            
        ]
